from datetime import date
from types import SimpleNamespace
from unittest import TestCase

from app.main import app
from app.services.opportunity_queue.queue import _queue_summary


class OpportunityQueueTests(TestCase):
    def test_opportunity_queue_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/opportunity-queue", paths)
        self.assertIn("get", paths["/api/opportunity-queue"])
        self.assertIn("post", paths["/api/opportunity-queue"])
        self.assertIn("/api/opportunity-queue/{opportunity_id}", paths)
        self.assertIn("patch", paths["/api/opportunity-queue/{opportunity_id}"])

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
