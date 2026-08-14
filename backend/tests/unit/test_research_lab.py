from decimal import Decimal
from unittest import TestCase

from app.main import app
from app.services.research_lab.lab import (
    _feature_status,
    _model_status,
)


class ResearchLabTests(TestCase):
    def test_research_lab_route_is_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/research-lab/overview", paths)
        self.assertIn("get", paths["/api/research-lab/overview"])
        self.assertIn("/api/research-lab/experiments", paths)
        self.assertIn("get", paths["/api/research-lab/experiments"])
        self.assertIn("/api/research-lab/backtests", paths)
        self.assertIn("get", paths["/api/research-lab/backtests"])
        self.assertIn("/api/research-lab/backtests/{backtest_id}", paths)
        self.assertIn("/api/research-lab/notes", paths)
        self.assertIn("post", paths["/api/research-lab/notes"])
        self.assertIn("/api/research-lab/notes/{note_id}", paths)
        self.assertIn("delete", paths["/api/research-lab/notes/{note_id}"])

    def test_feature_status_requires_meaningful_cross_section(self) -> None:
        self.assertEqual(
            _feature_status(snapshot_count=0, instrument_count=0, feature_count=0),
            "warning",
        )
        self.assertEqual(
            _feature_status(snapshot_count=10, instrument_count=2, feature_count=8),
            "warning",
        )
        self.assertEqual(
            _feature_status(snapshot_count=100, instrument_count=8, feature_count=8),
            "passed",
        )

    def test_model_status_separates_training_review_and_validated(self) -> None:
        self.assertEqual(_model_status(None, None, None), "training")
        self.assertEqual(
            _model_status(20, Decimal("56.00"), Decimal("-0.10")),
            "validated",
        )
        self.assertEqual(
            _model_status(20, Decimal("51.00"), Decimal("0.02")),
            "review",
        )
        self.assertEqual(
            _model_status(20, Decimal("49.00"), Decimal("-0.05")),
            "needs_review",
        )
