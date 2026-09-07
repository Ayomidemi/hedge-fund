from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest import TestCase

from app.main import app
from app.api.schemas.opportunity_queue import OpportunityLinks, OpportunityRiskLink
from app.services.opportunity_queue.queue import (
    STATUS_ORDER,
    default_strategy_pod_code,
    _paginate,
    _queue_summary,
    status_gate_error,
)


class OpportunityQueueTests(TestCase):
    def test_opportunity_queue_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/opportunity-queue", paths)
        self.assertIn("get", paths["/api/opportunity-queue"])
        self.assertIn("post", paths["/api/opportunity-queue"])
        self.assertIn("/api/opportunity-queue/{opportunity_id}", paths)
        self.assertIn("patch", paths["/api/opportunity-queue/{opportunity_id}"])

        get_params = {
            param["name"]
            for param in paths["/api/opportunity-queue"]["get"].get("parameters", [])
        }
        self.assertIn("page", get_params)
        self.assertIn("page_size", get_params)
        self.assertIn("status", get_params)

    def test_status_order_uses_parked_not_watchlist(self) -> None:
        self.assertIn("parked", STATUS_ORDER)
        self.assertNotIn("watchlist", STATUS_ORDER)

    def test_queue_summary_counts_active_and_priority_states(self) -> None:
        summary = _queue_summary(
            [
                SimpleNamespace(
                    status="approved",
                    priority="high",
                    review_by=date(2026, 8, 20),
                ),
                SimpleNamespace(
                    status="research",
                    priority="medium",
                    review_by=date(2026, 8, 15),
                ),
                SimpleNamespace(status="rejected", priority="urgent", review_by=None),
            ],
            candidate_count=4,
        )

        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.active, 2)
        self.assertEqual(summary.high_priority, 2)
        self.assertEqual(summary.approved, 1)
        self.assertEqual(summary.candidates, 4)
        self.assertEqual(summary.next_review_by, date(2026, 8, 15))
        self.assertEqual(summary.status_counts["approved"], 1)

    def test_paginate_slices_a_page(self) -> None:
        rows = list(range(45))
        page, page_size, total, total_pages, sliced = _paginate(rows, 2, 20)
        self.assertEqual(page, 2)
        self.assertEqual(page_size, 20)
        self.assertEqual(total, 45)
        self.assertEqual(total_pages, 3)
        self.assertEqual(sliced, list(range(20, 40)))

    def test_paginate_clamps_past_the_last_page(self) -> None:
        page, page_size, total, total_pages, sliced = _paginate(list(range(5)), 9, 20)
        self.assertEqual(page, 1)
        self.assertEqual(page_size, 20)
        self.assertEqual(total, 5)
        self.assertEqual(total_pages, 1)
        self.assertEqual(sliced, list(range(5)))

    def test_research_requires_a_memo(self) -> None:
        error = status_gate_error(
            "research",
            thesis="A thesis",
            research_question="Why?",
            target_weight=None,
            notes=None,
            links=OpportunityLinks(),
            source_memo_id=None,
        )
        self.assertIsNotNone(error)
        self.assertIn("memo", error.lower())

    def test_approved_requires_passing_pre_trade(self) -> None:
        error = status_gate_error(
            "approved",
            thesis="A thesis",
            research_question="Why?",
            target_weight="3",
            notes=None,
            links=OpportunityLinks(),
            source_memo_id=None,
        )
        self.assertIsNotNone(error)
        self.assertIn("pre-trade", error.lower())

    def test_approved_requires_linked_pre_trade(self) -> None:
        error = status_gate_error(
            "approved",
            thesis="A thesis",
            research_question="Why?",
            target_weight="3",
            notes=None,
            links=OpportunityLinks(
                pre_trade=OpportunityRiskLink(
                    id=uuid4(),
                    decision="approve",
                    risk_level="low",
                    checked_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                    linked=False,
                )
            ),
            source_memo_id=None,
        )
        self.assertIsNotNone(error)
        self.assertIn("link", error.lower())

    def test_candidate_requires_target_weight(self) -> None:
        error = status_gate_error(
            "candidate",
            thesis="A thesis",
            research_question="Why?",
            target_weight=None,
            notes=None,
            links=OpportunityLinks(),
            source_memo_id="memo",
        )
        self.assertIsNotNone(error)
        self.assertIn("target weight", error.lower())

    def test_default_pod_assignment_rules(self) -> None:
        equity = SimpleNamespace(ticker="AAPL")
        spy = SimpleNamespace(ticker="SPY")
        self.assertEqual(default_strategy_pod_code(equity), "fundamental_equity")
        self.assertEqual(default_strategy_pod_code(spy), "cross_asset_trend")
        self.assertEqual(
            default_strategy_pod_code(
                equity,
                discovery_evidence={"reasons": ["capital rotation beneficiary"]},
            ),
            "relative_value",
        )
