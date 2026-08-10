from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from app.services.risk.risk_centre import (
    PortfolioMarketStats,
    PortfolioRiskState,
    RiskPosition,
    build_risk_overview_from_state,
    risk_level_from_measurements,
    run_stress_scenario,
    _json_payload,
)


class RiskCentreTests(TestCase):
    def test_policy_flags_concentration_and_cash_breaches(self) -> None:
        state = PortfolioRiskState(
            portfolio_id=uuid4(),
            portfolio_name="Test Fund",
            calculated_at=datetime.now(timezone.utc),
            as_of_date=date(2026, 8, 10),
            nav=Decimal("1000"),
            cash_balance=Decimal("50"),
            invested_value=Decimal("950"),
            positions=[
                RiskPosition(
                    instrument_id=uuid4(),
                    ticker="AAPL",
                    name="Apple Inc.",
                    asset_class="equity",
                    sector="Technology",
                    quantity=Decimal("10"),
                    average_cost=Decimal("80"),
                    market_value=Decimal("700"),
                    unrealized_pnl=Decimal("0"),
                ),
                RiskPosition(
                    instrument_id=uuid4(),
                    ticker="MSFT",
                    name="Microsoft Corp.",
                    asset_class="equity",
                    sector="Technology",
                    quantity=Decimal("5"),
                    average_cost=Decimal("50"),
                    market_value=Decimal("250"),
                    unrealized_pnl=Decimal("0"),
                ),
            ],
        )

        overview = build_risk_overview_from_state(state)
        failed_keys = {check.key for check in overview.measurements if not check.passed}

        self.assertIn("max_single_equity_position_pct", failed_keys)
        self.assertIn("max_sector_exposure_pct", failed_keys)
        self.assertIn("min_cash_allocation_pct", failed_keys)
        self.assertEqual(overview.snapshot.risk_level, "reduce")

    def test_stress_scenario_calculates_nav_impact(self) -> None:
        state = PortfolioRiskState(
            portfolio_id=uuid4(),
            portfolio_name="Test Fund",
            calculated_at=datetime.now(timezone.utc),
            as_of_date=date(2026, 8, 10),
            nav=Decimal("1000"),
            cash_balance=Decimal("200"),
            invested_value=Decimal("800"),
            positions=[
                RiskPosition(
                    instrument_id=uuid4(),
                    ticker="SPY",
                    name="SPDR S&P 500 ETF",
                    asset_class="etf",
                    sector="ETF",
                    quantity=Decimal("8"),
                    average_cost=Decimal("100"),
                    market_value=Decimal("800"),
                    unrealized_pnl=Decimal("0"),
                ),
            ],
        )

        result = run_stress_scenario(
            state,
            {
                "name": "Market -10%",
                "scenario_type": "market",
                "market_shock_pct": Decimal("-10"),
                "sector_shocks_pct": {},
                "ticker_shocks_pct": {},
                "cash_shock_pct": Decimal("0"),
                "notes": [],
            },
        )

        self.assertEqual(result.nav_after, Decimal("920.00"))
        self.assertEqual(result.nav_impact_pct, Decimal("-8.00"))
        self.assertEqual(result.severity, "warning")

    def test_risk_level_is_normal_when_everything_passes(self) -> None:
        self.assertEqual(risk_level_from_measurements([]), "normal")

    def test_market_stats_do_not_force_failures_when_unavailable(self) -> None:
        stats = PortfolioMarketStats()
        self.assertIsNone(stats.portfolio_volatility_pct)

    def test_json_payload_converts_decimal_values(self) -> None:
        payload = _json_payload(
            {
                "market_shock_pct": Decimal("-8"),
                "ticker_shocks_pct": {"AAPL": Decimal("-12.5")},
            }
        )

        self.assertEqual(payload["market_shock_pct"], "-8")
        self.assertEqual(payload["ticker_shocks_pct"]["AAPL"], "-12.5")
