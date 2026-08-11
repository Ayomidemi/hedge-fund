from decimal import Decimal
from unittest import TestCase

from pydantic import ValidationError

from app.api.schemas.strategy_pods import StrategyPodUpdate
from app.services.strategy_pods.pods import (
    DEFAULT_STRATEGY_POD_DEFINITIONS,
    POD_LIFECYCLE_ORDER,
    POD_STATUS_ORDER,
    normalize_strategy_pod_code,
    strategy_pod_allocation_recommendation,
)


class StrategyPodTests(TestCase):
    def test_default_pods_cover_scope_sections(self) -> None:
        codes = {pod["code"] for pod in DEFAULT_STRATEGY_POD_DEFINITIONS}

        self.assertEqual(
            codes,
            {
                "macro_regime",
                "cross_asset_trend",
                "quant_equity",
                "fundamental_equity",
                "relative_value",
                "experimental_research",
            },
        )

    def test_default_live_allocation_leaves_reserve(self) -> None:
        allocation = sum(
            pod["capital_allocation_pct"] for pod in DEFAULT_STRATEGY_POD_DEFINITIONS
        )

        self.assertLessEqual(allocation, Decimal("100"))
        self.assertEqual(allocation, Decimal("90.0000"))

    def test_portfolio_halt_overrides_pod_signal(self) -> None:
        recommendation = strategy_pod_allocation_recommendation(
            code="quant_equity",
            status="active",
            lifecycle_stage="paper_trading",
            risk_level="halt",
            capital_allocation_pct=Decimal("25"),
            current_signal_score=Decimal("80"),
            model_confidence=Decimal("80"),
        )

        self.assertIn("halt", recommendation.lower())

    def test_research_pod_does_not_get_live_allocation(self) -> None:
        recommendation = strategy_pod_allocation_recommendation(
            code="experimental_research",
            status="sandbox",
            lifecycle_stage="research",
            risk_level="normal",
            capital_allocation_pct=Decimal("0"),
            current_signal_score=Decimal("90"),
            model_confidence=Decimal("90"),
        )

        self.assertIn("research-only", recommendation.lower())

    def test_macro_stress_regime_is_defensive(self) -> None:
        recommendation = strategy_pod_allocation_recommendation(
            code="macro_regime",
            status="active",
            lifecycle_stage="paper_trading",
            risk_level="normal",
            capital_allocation_pct=Decimal("20"),
            current_regime="stress",
            current_signal_score=Decimal("30"),
            model_confidence=Decimal("75"),
        )

        self.assertIn("defensive", recommendation.lower())

    def test_code_normalization_accepts_url_friendly_slugs(self) -> None:
        self.assertEqual(
            normalize_strategy_pod_code("Cross-Asset-Trend"), "cross_asset_trend"
        )

    def test_update_schema_rejects_unknown_status(self) -> None:
        with self.assertRaises(ValidationError):
            StrategyPodUpdate(status="maybe-active")

    def test_update_schema_rejects_unknown_lifecycle_stage(self) -> None:
        with self.assertRaises(ValidationError):
            StrategyPodUpdate(lifecycle_stage="launch_live_now")

    def test_default_pod_states_are_in_approved_vocabulary(self) -> None:
        for pod in DEFAULT_STRATEGY_POD_DEFINITIONS:
            self.assertIn(pod["status"], POD_STATUS_ORDER)
            self.assertIn(pod["lifecycle_stage"], POD_LIFECYCLE_ORDER)

    def test_invalid_existing_state_requires_governance_review(self) -> None:
        recommendation = strategy_pod_allocation_recommendation(
            code="quant_equity",
            status="live-ish",
            lifecycle_stage="paper_trading",
            risk_level="normal",
            capital_allocation_pct=Decimal("25"),
            current_signal_score=Decimal("80"),
            model_confidence=Decimal("80"),
        )

        self.assertIn("governance review", recommendation.lower())
