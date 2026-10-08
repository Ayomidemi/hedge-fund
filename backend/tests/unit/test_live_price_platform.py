from datetime import datetime, timezone
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

import httpx

from app.core.config import settings
from app.services.market_data.ingestion import is_us_market_open
from app.services.market_data.quote_provider import (
    LiveQuote,
    _clear_provider_backoff,
    _decimal,
    _epoch_datetime,
    _fetch_fmp_quotes,
    _fetch_polygon_prev_close,
    _int,
    _iso_datetime,
    fetch_quotes,
)
from app.services.market_data.tiingo_stream import (
    build_subscribe_message,
    parse_fx_message,
    parse_iex_reference_message,
)
from app.services.market_data.fx_convert import convert_to_usd, is_nigerian_instrument
from app.services.realtime.events import (
    EVENT_FX_RATE_UPDATED,
    EVENT_PORTFOLIO_MARKED,
    EVENT_QUOTE_BATCH_UPDATED,
    fx_rate_updated_event,
    portfolio_marked_event,
    quote_batch_updated_event,
    system_log_entry_event,
)
from app.workers.celery_app import celery_app


class MarketHoursTests(TestCase):
    def test_open_during_us_session(self) -> None:
        # Tuesday 15:00 UTC
        self.assertTrue(
            is_us_market_open(datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc))
        )

    def test_closed_overnight(self) -> None:
        # Tuesday 03:00 UTC
        self.assertFalse(
            is_us_market_open(datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc))
        )

    def test_closed_on_weekend(self) -> None:
        # Saturday 15:00 UTC
        self.assertFalse(
            is_us_market_open(datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc))
        )


class QuoteParsingTests(TestCase):
    def test_decimal_parsing(self) -> None:
        self.assertEqual(_decimal("227.50"), Decimal("227.50"))
        self.assertEqual(_decimal(12), Decimal("12"))
        self.assertIsNone(_decimal(None))
        self.assertIsNone(_decimal(""))
        self.assertIsNone(_decimal("not-a-number"))

    def test_int_parsing(self) -> None:
        self.assertEqual(_int("1200.0"), 1200)
        self.assertIsNone(_int(None))
        self.assertIsNone(_int("abc"))

    def test_epoch_seconds_and_milliseconds(self) -> None:
        seconds = _epoch_datetime(1_780_000_000)
        milliseconds = _epoch_datetime(1_780_000_000_000)
        self.assertIsNotNone(seconds)
        self.assertIsNotNone(milliseconds)
        self.assertEqual(seconds, milliseconds)
        self.assertIsNone(_epoch_datetime("bad"))
        self.assertIsNone(_epoch_datetime(0))

    def test_iso_datetime_handles_zulu_suffix(self) -> None:
        parsed = _iso_datetime("2026-08-11T14:30:00Z")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.tzinfo is not None, True)
        self.assertIsNone(_iso_datetime("nope"))

    def test_tiingo_reference_price_stream_message(self) -> None:
        quote = parse_iex_reference_message(
            {
                "service": "iex",
                "messageType": "A",
                "data": ["2026-08-24T14:30:00Z", "nvda", 182.25],
            },
            received_at=datetime(2026, 8, 24, 14, 30, 1, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(quote)
        assert quote is not None
        self.assertEqual(quote.ticker, "NVDA")
        self.assertEqual(quote.price, Decimal("182.25"))
        self.assertEqual(quote.source, "tiingo_stream")
        self.assertEqual(quote.raw_payload["stream_status"], "live")

    def test_tiingo_fx_stream_message(self) -> None:
        rate = parse_fx_message(
            {
                "service": "fx",
                "messageType": "A",
                "data": [
                    "Q",
                    "usdngn",
                    "2026-08-24T14:30:00Z",
                    1,
                    1530,
                    1531.5,
                    1533,
                    1,
                ],
            }
        )
        self.assertIsNotNone(rate)
        assert rate is not None
        self.assertEqual(rate.base_currency, "USD")
        self.assertEqual(rate.quote_currency, "NGN")
        self.assertEqual(rate.rate, Decimal("1531.5"))
        self.assertEqual(rate.source, "tiingo_stream")

    def test_tiingo_subscribe_message_redaction_boundary(self) -> None:
        message = build_subscribe_message(
            token="secret-token",
            threshold_level=6,
            tickers=["NVDA", "AAPL"],
        )
        self.assertIn('"authorization": "secret-token"', message)
        self.assertIn('"authToken": "secret-token"', message)
        self.assertIn('"thresholdLevel": 6', message)
        self.assertIn('"nvda"', message)
        self.assertIn('"aapl"', message)


class FxConversionTests(TestCase):
    def test_ngn_trade_cannot_be_silently_valued_as_usd_in_an_eur_portfolio(self):
        from app.models import FxRate, Instrument
        from app.services.market_data.fx_convert import price_in_portfolio_base
        rates = {("USD", "NGN"): FxRate(rate=Decimal("1500"))}
        instrument = Instrument(ticker="NGTEST", currency="NGN", asset_class="equity")
        self.assertIsNone(price_in_portfolio_base(Decimal("15000"), instrument, "EUR", rates))
        self.assertEqual(price_in_portfolio_base(Decimal("15000"), instrument, "USD", rates), Decimal("10"))

    def test_convert_ngn_to_usd(self) -> None:
        from app.models import FxRate

        rate_row = FxRate(
            base_currency="USD",
            quote_currency="NGN",
            rate=Decimal("1363.18"),
            source="er-api",
            as_of=datetime.now(timezone.utc),
        )
        fx_rates = {("USD", "NGN"): rate_row}
        converted = convert_to_usd(Decimal("13631.80"), "NGN", fx_rates)
        self.assertEqual(converted, Decimal("10"))

    def test_nigerian_instrument_detection(self) -> None:
        from app.models import Instrument

        ng = Instrument(
            ticker="SEPLAT",
            name="Seplat",
            asset_class="equity",
            exchange="NG",
            currency="USD",
        )
        self.assertTrue(is_nigerian_instrument(ng))


class EventEnvelopeTests(TestCase):
    def test_quote_batch_event_broadcasts_to_everyone(self) -> None:
        event = quote_batch_updated_event(
            quotes=[{"ticker": "AAPL", "price": "227.50"}],
            as_of="2026-08-11T14:30:00+00:00",
        )
        self.assertEqual(event["type"], EVENT_QUOTE_BATCH_UPDATED)
        self.assertIsNone(event["owner_user_id"])
        self.assertEqual(event["payload"]["quotes"][0]["ticker"], "AAPL")

    def test_portfolio_marked_event_targets_owner(self) -> None:
        event = portfolio_marked_event(
            owner_user_id="user-1",
            portfolio_id="pf-1",
            nav="1050.00",
            cash_balance="500.00",
            invested_value="550.00",
            position_count=3,
        )
        self.assertEqual(event["type"], EVENT_PORTFOLIO_MARKED)
        self.assertEqual(event["owner_user_id"], "user-1")
        self.assertEqual(event["payload"]["nav"], "1050.00")

    def test_fx_rate_updated_event_broadcasts(self) -> None:
        event = fx_rate_updated_event(
            base_currency="USD",
            quote_currency="NGN",
            rate="1363.18",
            source="er-api",
            as_of="2026-08-11T14:30:00+00:00",
        )
        self.assertEqual(event["type"], EVENT_FX_RATE_UPDATED)
        self.assertEqual(event["payload"]["pair_label"], "USD/NGN")

    def test_system_log_event_includes_message(self) -> None:
        event = system_log_entry_event(
            owner_user_id=None,
            level="info",
            category="market_data",
            event="price_refresh_completed",
            message="Refreshed 10/10 quotes.",
        )
        self.assertEqual(event["payload"]["category"], "market_data")


class QuoteProviderRateLimitTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _clear_provider_backoff()

    def tearDown(self) -> None:
        _clear_provider_backoff()

    async def test_fmp_stops_after_one_rate_limit_and_stays_quiet(self) -> None:
        client = _status_error_client(429)
        with patch(
            "app.services.market_data.quote_provider.httpx.AsyncClient",
            return_value=client,
        ):
            first = await _fetch_fmp_quotes(["AAA", "BBB", "CCC"])
            second = await _fetch_fmp_quotes(["DDD"])

        self.assertEqual(first, {})
        self.assertEqual(second, {})
        self.assertEqual(client.get.await_count, 1)

    async def test_fmp_stops_after_one_payment_required(self) -> None:
        client = _status_error_client(402)
        with patch(
            "app.services.market_data.quote_provider.httpx.AsyncClient",
            return_value=client,
        ):
            first = await _fetch_fmp_quotes(["EXYN", "EYPT", "FBDT"])
            second = await _fetch_fmp_quotes(["NVDA"])

        self.assertEqual(first, {})
        self.assertEqual(second, {})
        self.assertEqual(client.get.await_count, 1)

    async def test_polygon_stops_after_one_rate_limit_and_stays_quiet(self) -> None:
        client = _status_error_client(429)
        with patch(
            "app.services.market_data.quote_provider.httpx.AsyncClient",
            return_value=client,
        ):
            first = await _fetch_polygon_prev_close(["AAA", "BBB"])
            second = await _fetch_polygon_prev_close(["CCC"])

        self.assertEqual(first, {})
        self.assertEqual(second, {})
        self.assertEqual(client.get.await_count, 1)

    async def test_fmp_is_skipped_when_tiingo_answers(self) -> None:
        quote = _sample_quote("NVDA")
        with (
            patch(
                "app.services.market_data.quote_provider.settings.hf_tiingo_api_key",
                "tiingo-key",
            ),
            patch(
                "app.services.market_data.quote_provider.settings.hf_fmp_api_key",
                "fmp-key",
            ),
            patch(
                "app.services.market_data.quote_provider.settings.hf_polygon_api_key",
                "polygon-key",
            ),
            patch(
                "app.services.market_data.quote_provider._fetch_tiingo_iex",
                new=AsyncMock(return_value=({"NVDA": quote}, True)),
            ),
            patch(
                "app.services.market_data.quote_provider._fetch_fmp_quotes",
                new=AsyncMock(),
            ) as fmp,
            patch(
                "app.services.market_data.quote_provider._fetch_polygon_prev_close",
                new=AsyncMock(),
            ) as polygon,
        ):
            quotes = await fetch_quotes(["NVDA", "EXYN"])

        self.assertEqual(set(quotes), {"NVDA"})
        fmp.assert_not_awaited()
        polygon.assert_not_awaited()

    async def test_fmp_runs_only_when_tiingo_is_unavailable(self) -> None:
        quote = _sample_quote("NVDA", source="fmp")
        with (
            patch(
                "app.services.market_data.quote_provider.settings.hf_tiingo_api_key",
                "tiingo-key",
            ),
            patch(
                "app.services.market_data.quote_provider.settings.hf_fmp_api_key",
                "fmp-key",
            ),
            patch(
                "app.services.market_data.quote_provider.settings.hf_polygon_api_key",
                None,
            ),
            patch(
                "app.services.market_data.quote_provider._fetch_tiingo_iex",
                new=AsyncMock(return_value=({}, False)),
            ),
            patch(
                "app.services.market_data.quote_provider._fetch_fmp_quotes",
                new=AsyncMock(return_value={"NVDA": quote}),
            ) as fmp,
        ):
            quotes = await fetch_quotes(["NVDA"])

        self.assertEqual(quotes["NVDA"].source, "fmp")
        fmp.assert_awaited_once()


def _sample_quote(ticker: str, source: str = "tiingo") -> LiveQuote:
    return LiveQuote(
        ticker=ticker,
        price=Decimal("100"),
        source=source,
        as_of=datetime(2026, 10, 5, tzinfo=timezone.utc),
    )


def _status_error_client(status_code: int) -> AsyncMock:
    request = httpx.Request("GET", "https://example.test/quote")
    response = httpx.Response(status_code, request=request)
    error = httpx.HTTPStatusError(str(status_code), request=request, response=response)

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = error
    return client


class CelerySchedulingTests(TestCase):
    def test_beat_interval_comes_from_settings(self) -> None:
        schedule = celery_app.conf.beat_schedule["price-refresh"]
        self.assertEqual(
            schedule["schedule"],
            float(settings.price_refresh_interval_seconds),
        )
        self.assertEqual(schedule["task"], "price_refresh.run")

    def test_interval_has_sane_floor(self) -> None:
        self.assertGreaterEqual(settings.price_refresh_interval_seconds, 5)

    def test_radar_scan_is_on_the_beat_schedule(self) -> None:
        from app.core.market_constants import RADAR_SCAN_INTERVAL_SECONDS

        schedule = celery_app.conf.beat_schedule["market-radar"]
        self.assertEqual(schedule["task"], "radar.scan")
        self.assertEqual(schedule["schedule"], float(RADAR_SCAN_INTERVAL_SECONDS))


class UnusableTiingoFallbackTests(IsolatedAsyncioTestCase):
    async def test_reference_response_without_any_provider_timestamp_uses_backup(self):
        # A reference price without a provider timestamp cannot be used.
        _clear_provider_backoff()
        response = httpx.Response(200, request=httpx.Request('GET', 'https://example.test/iex'), json=[{
            'ticker': 'SPY', 'tngoLast': 100, 'timestamp': None,
            'lastSaleTimestamp': None, 'last': None,
        }])
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.get.return_value = response
        backup = _sample_quote('SPY', source='fmp')
        with patch('app.services.market_data.quote_provider.httpx.AsyncClient', return_value=client), patch('app.services.market_data.quote_provider.settings.hf_tiingo_api_key', 'test'), patch('app.services.market_data.quote_provider.settings.hf_fmp_api_key', 'test'), patch('app.services.market_data.quote_provider._fetch_fmp_quotes', AsyncMock(return_value={'SPY': backup})) as fallback:
            quotes = await fetch_quotes(['SPY'])
        fallback.assert_awaited_once_with(['SPY'])
        self.assertIs(quotes['SPY'], backup)

    async def test_empty_success_response_uses_backup(self):
        from app.services.market_data.quote_provider import _fetch_tiingo_iex
        _clear_provider_backoff()
        response = httpx.Response(200, request=httpx.Request('GET', 'https://example.test/iex'), json=[])
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.get.return_value = response
        with patch('app.services.market_data.quote_provider.httpx.AsyncClient', return_value=client):
            quotes, available = await _fetch_tiingo_iex(['SPY'])
        self.assertEqual(quotes, {})
        self.assertFalse(available)
