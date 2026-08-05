from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase

from app.services.ticker_intelligence.market_data import (
    PrefillBuildContext,
    _build_prefill_response,
    normalize_massive_base_url,
)


class MarketDataPrefillTests(TestCase):
    def test_massive_web_host_normalizes_to_api_host(self) -> None:
        self.assertEqual(
            normalize_massive_base_url("https://massive.com"),
            "https://api.massive.com",
        )

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
