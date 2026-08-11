from decimal import Decimal
from unittest import TestCase

from app.services.portfolio.calculations import (
    DEFAULT_RISK_LIMITS,
    PositionSnapshot,
    calculate_nav,
    evaluate_risk_limits,
    group_exposure_by_asset_class,
    group_exposure_by_sector,
    money,
    percent,
)


class PortfolioCalculationTests(TestCase):
    def test_calculates_nav_from_cash_and_positions(self) -> None:
        positions = [
            PositionSnapshot(
                ticker="AAPL",
                asset_class="equity",
                sector="Technology",
                market_value=Decimal("50"),
            ),
            PositionSnapshot(
                ticker="SPY",
                asset_class="etf",
                sector="Broad Market",
                market_value=Decimal("250"),
            ),
        ]

        self.assertEqual(calculate_nav(Decimal("700"), positions), Decimal("1000.00"))

    def test_groups_exposure_by_asset_class_and_sector(self) -> None:
        positions = [
            PositionSnapshot("AAPL", "equity", "Technology", Decimal("50")),
            PositionSnapshot("MSFT", "equity", "Technology", Decimal("40")),
            PositionSnapshot("SPY", "etf", "Broad Market", Decimal("250")),
        ]

        self.assertEqual(
            group_exposure_by_asset_class(positions, Decimal("1000")),
            {"equity": Decimal("9.00"), "etf": Decimal("25.00")},
        )
        self.assertEqual(
            group_exposure_by_sector(positions, Decimal("1000")),
            {"Broad Market": Decimal("25.00"), "Technology": Decimal("9.00")},
        )

    def test_evaluates_phase_one_risk_limits(self) -> None:
        positions = [
            PositionSnapshot("AAPL", "equity", "Technology", Decimal("70")),
            PositionSnapshot("SPY", "etf", "Broad Market", Decimal("260")),
        ]
        checks = evaluate_risk_limits(
            cash_balance=Decimal("670"),
            positions=positions,
            nav=Decimal("1000"),
            risk_limits=DEFAULT_RISK_LIMITS,
        )
        checks_by_type = {check.limit_type: check for check in checks}

        self.assertFalse(checks_by_type["max_single_equity_position_pct"].passed)
        self.assertFalse(checks_by_type["max_etf_position_pct"].passed)
        self.assertTrue(checks_by_type["min_cash_allocation_pct"].passed)
        self.assertTrue(checks_by_type["max_leverage_pct"].passed)

    def test_negative_cash_flags_leverage_and_cash_limit(self) -> None:
        checks = evaluate_risk_limits(
            cash_balance=Decimal("-25"),
            positions=[PositionSnapshot("SPY", "etf", "Broad Market", Decimal("1025"))],
            nav=Decimal("1000"),
            risk_limits=DEFAULT_RISK_LIMITS,
        )
        checks_by_type = {check.limit_type: check for check in checks}

        self.assertFalse(checks_by_type["min_cash_allocation_pct"].passed)
        self.assertFalse(checks_by_type["max_leverage_pct"].passed)
        self.assertEqual(
            checks_by_type["max_leverage_pct"].observed_value, Decimal("2.50")
        )

    def test_percent_returns_zero_when_denominator_is_zero(self) -> None:
        self.assertEqual(percent(Decimal("10"), Decimal("0")), Decimal("0"))

    def test_money_accepts_empty_sum_integer_zero(self) -> None:
        self.assertEqual(money(sum([])), Decimal("0.00"))
