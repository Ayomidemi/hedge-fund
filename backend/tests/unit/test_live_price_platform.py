from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase

from app.core.config import settings
from app.services.market_data.ingestion import is_us_market_open
from app.services.market_data.quote_provider import (
    _decimal,
    _epoch_datetime,
    _int,
    _iso_datetime,
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


class FxConversionTests(TestCase):
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
