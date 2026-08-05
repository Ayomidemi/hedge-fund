from decimal import Decimal
from unittest import TestCase

from app.api.schemas.ticker_intelligence import TickerMetricsInput
from app.services.ticker_intelligence.scoring import (
    action_from_score,
    recommended_weight_from_score,
    score_ticker,
)


class TickerIntelligenceScoringTests(TestCase):
    def test_strong_manual_metrics_create_candidate_score(self) -> None:
        scorecard = score_ticker(
            TickerMetricsInput(
                pe_ratio=Decimal("22"),
                forward_pe=Decimal("18"),
                revenue_growth_pct=Decimal("18"),
                earnings_growth_pct=Decimal("21"),
                free_cash_flow_yield_pct=Decimal("4.5"),
                net_margin_pct=Decimal("24"),
                debt_to_equity=Decimal("0.35"),
                price_vs_200d_pct=Decimal("14"),
                relative_strength_6m_pct=Decimal("11"),
                volatility_30d_pct=Decimal("24"),
            ),
            asset_class="equity",
        )

        self.assertGreaterEqual(scorecard.composite_score, Decimal("70"))
        self.assertGreaterEqual(scorecard.confidence_score, Decimal("80"))
        self.assertIn(scorecard.action, {"buy", "hold"})
        self.assertGreater(scorecard.recommended_weight, Decimal("0"))

    def test_sparse_metrics_stay_on_watch_even_with_neutral_score(self) -> None:
        scorecard = score_ticker(
            TickerMetricsInput(pe_ratio=Decimal("18")),
            asset_class="equity",
        )

        self.assertEqual(scorecard.action, "watch")
        self.assertEqual(scorecard.classification, "data-incomplete watchlist")
        self.assertEqual(scorecard.recommended_weight, Decimal("0.0000"))

    def test_etf_weight_cap_is_larger_than_single_equity_cap(self) -> None:
        equity_weight = recommended_weight_from_score(
            Decimal("95"),
            Decimal("90"),
            "equity",
        )
        etf_weight = recommended_weight_from_score(
            Decimal("95"),
            Decimal("90"),
            "etf",
        )

        self.assertGreater(etf_weight, equity_weight)
        self.assertLessEqual(equity_weight, Decimal("0.0500"))
        self.assertLessEqual(etf_weight, Decimal("0.2000"))

    def test_low_score_is_avoid_action(self) -> None:
        self.assertEqual(action_from_score(Decimal("30"), Decimal("90")), "avoid")
