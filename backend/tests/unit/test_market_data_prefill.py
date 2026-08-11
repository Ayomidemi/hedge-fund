from datetime import datetime, timezone
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.services.ticker_intelligence.market_data import (
    PrefillBuildContext,
    _build_prefill_response,
    normalize_massive_base_url,
    prefill_ticker,
    resolve_ticker,
)


class MarketDataPrefillTests(TestCase):
    def test_massive_web_host_normalizes_to_api_host(self) -> None:
        self.assertEqual(
            normalize_massive_base_url("https://massive.com"),
            "https://api.massive.com",
        )

    def test_resolves_nigerian_market_tickers(self) -> None:
        suffix_resolution = resolve_ticker("dangcem.ng")
        hint_resolution = resolve_ticker("dangcem", market_hint="NG")
        prefix_resolution = resolve_ticker("ngx:dangcem")

        self.assertEqual(suffix_resolution.ticker, "DANGCEM.NG")
        self.assertEqual(hint_resolution.ticker, "DANGCEM.NG")
        self.assertEqual(prefix_resolution.provider_symbol, "DANGCEM")
        self.assertEqual(prefix_resolution.market, "NG")

    def test_builds_prefill_from_details_ratios_and_bars(self) -> None:
        bars = []
        base_price = Decimal("100")
        for index in range(220):
            close = base_price + Decimal(index) / Decimal("10")
            bars.append(
                {
                    "c": str(close),
                    "t": int(
                        datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
                    )
                    + (index * 86_400_000),
                }
            )

        response = _build_prefill_response(
            PrefillBuildContext(
                ticker="AAPL",
                details={
                    "name": "Apple Inc.",
                    "primary_exchange": "XNAS",
                    "currency_name": "usd",
                    "market_cap": 3_000_000_000_000,
                    "sic_description": "Technology Hardware",
                    "type": "CS",
                },
                ratios={
                    "price": 220,
                    "market_cap": 3_200_000_000_000,
                    "price_to_earnings": 32.5,
                    "free_cash_flow": 100_000_000_000,
                    "debt_to_equity": 1.2,
                    "net_margin": 0.25,
                },
                bars=bars,
            )
        )

        self.assertEqual(response.instrument.ticker, "AAPL")
        self.assertEqual(response.instrument.name, "Apple Inc.")
        self.assertEqual(response.instrument.asset_class, "equity")
        self.assertEqual(response.metrics.current_price, Decimal("220"))
        self.assertEqual(response.metrics.market_cap_billion, Decimal("3200.00"))
        self.assertEqual(response.metrics.pe_ratio, Decimal("32.5"))
        self.assertEqual(response.metrics.free_cash_flow_yield_pct, Decimal("3.13"))
        self.assertEqual(response.metrics.net_margin_pct, Decimal("25.00"))
        self.assertIsNotNone(response.metrics.price_vs_200d_pct)
        self.assertIsNotNone(response.metrics.relative_strength_6m_pct)
        self.assertIsNotNone(response.metrics.volatility_30d_pct)

    def test_builds_prefill_from_fmp_fallback_fields(self) -> None:
        response = _build_prefill_response(
            PrefillBuildContext(
                ticker="VOO",
                provider_symbol="VOO",
                fmp_profile={
                    "companyName": "Vanguard S&P 500 ETF",
                    "currency": "USD",
                    "exchangeShortName": "AMEX",
                    "type": "ETF",
                    "price": 500.25,
                    "mktCap": 600_000_000_000,
                },
                fmp_quote={"pe": 24.1},
                fmp_key_metrics={"freeCashFlowYieldTTM": 0.039},
                providers=["fmp"],
            )
        )

        self.assertEqual(response.instrument.name, "Vanguard S&P 500 ETF")
        self.assertEqual(response.instrument.asset_class, "etf")
        self.assertEqual(response.instrument.exchange, "AMEX")
        self.assertEqual(response.metrics.current_price, Decimal("500.25"))
        self.assertEqual(response.metrics.market_cap_billion, Decimal("600.00"))
        self.assertEqual(response.metrics.pe_ratio, Decimal("24.1"))
        self.assertEqual(response.metrics.free_cash_flow_yield_pct, Decimal("3.90"))

    def test_hides_provider_plan_warnings_when_fallback_data_prefills(self) -> None:
        response = _build_prefill_response(
            PrefillBuildContext(
                ticker="NVDA",
                provider_symbol="NVDA",
                details={"name": "NVIDIA Corporation", "primary_exchange": "XNAS"},
                bars=[{"c": "180.25"}],
                warnings=[
                    "/stocks/financials/v1/ratios not available for this API key or plan.",
                    "/v3/profile/NVDA not available for this API key or plan.",
                    "/v3/reference/tickers/NVDA returned 404: not found",
                    "Temporary provider timeout.",
                ],
            )
        )

        self.assertEqual(response.instrument.name, "NVIDIA Corporation")
        self.assertEqual(response.metrics.current_price, Decimal("180.25"))
        self.assertEqual(response.source_warnings, ["Temporary provider timeout."])

    def test_builds_prefill_from_ngn_market_fields(self) -> None:
        response = _build_prefill_response(
            PrefillBuildContext(
                ticker="DANGCEM.NG",
                provider_symbol="DANGCEM",
                market="NG",
                ngn_company={
                    "name": "Dangote Cement Plc",
                    "sector": "Industrial Goods",
                    "industry": "Building Materials",
                    "currentPrice": 480,
                    "marketCap": 8_000_000_000_000,
                    "peRatio": 18.7,
                },
                providers=["ngnmarket"],
            )
        )

        self.assertEqual(response.instrument.ticker, "DANGCEM.NG")
        self.assertEqual(response.instrument.name, "Dangote Cement Plc")
        self.assertEqual(response.instrument.exchange, "NGX")
        self.assertEqual(response.instrument.currency, "NGN")
        self.assertEqual(response.metrics.current_price, Decimal("480"))
        self.assertEqual(response.metrics.market_cap_billion, Decimal("8000.00"))
        self.assertEqual(response.metrics.pe_ratio, Decimal("18.7"))


class MarketDataPrefillRoutingTests(IsolatedAsyncioTestCase):
    async def test_ng_market_hint_only_calls_ngn_sources(self) -> None:
        with (
            patch(
                "app.services.ticker_intelligence.market_data._has_market_data_key",
                return_value=True,
            ),
            patch(
                "app.services.ticker_intelligence.market_data._load_us_sources",
                new_callable=AsyncMock,
            ) as load_us_sources,
            patch(
                "app.services.ticker_intelligence.market_data._load_ngn_market_sources",
                new_callable=AsyncMock,
            ) as load_ngn_market_sources,
        ):
            response = await prefill_ticker("DANGCEM", market_hint="NG")

        self.assertEqual(response.instrument.ticker, "DANGCEM.NG")
        load_ngn_market_sources.assert_awaited_once()
        load_us_sources.assert_not_awaited()

    async def test_us_market_hint_only_calls_us_sources(self) -> None:
        with (
            patch(
                "app.services.ticker_intelligence.market_data._has_market_data_key",
                return_value=True,
            ),
            patch(
                "app.services.ticker_intelligence.market_data._load_us_sources",
                new_callable=AsyncMock,
            ) as load_us_sources,
            patch(
                "app.services.ticker_intelligence.market_data._load_ngn_market_sources",
                new_callable=AsyncMock,
            ) as load_ngn_market_sources,
        ):
            response = await prefill_ticker("MTN", market_hint="US")

        self.assertEqual(response.instrument.ticker, "MTN")
        load_us_sources.assert_awaited_once()
        load_ngn_market_sources.assert_not_awaited()
