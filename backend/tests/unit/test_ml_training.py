from datetime import date, timedelta
from decimal import Decimal
from unittest import TestCase

from app.services.ticker_intelligence.ml_training import (
    PriceBarPoint,
    compute_portfolio_fit_score,
    compute_price_feature_snapshots,
    compute_forward_labels,
    _latest_fundamental_features_as_of,
)
from app.models import TickerFeatureSnapshot


class MLTrainingTests(TestCase):
    def test_compute_forward_labels_with_relative_return_and_risk(self) -> None:
        start_date = date(2026, 1, 1)
        prices = [
            Decimal("100"),
            Decimal("105"),
            Decimal("102"),
            Decimal("110"),
            Decimal("115"),
        ]
        benchmark_prices = [
            Decimal("100"),
            Decimal("101"),
            Decimal("102"),
            Decimal("103"),
            Decimal("104"),
        ]
        bars = [
            PriceBarPoint(start_date + timedelta(days=index), price)
            for index, price in enumerate(prices)
        ]
        benchmark_bars = [
            PriceBarPoint(start_date + timedelta(days=index), price)
            for index, price in enumerate(benchmark_prices)
        ]

        labels = compute_forward_labels(bars, horizons=[2], benchmark_bars=benchmark_bars)

        self.assertEqual(len(labels), 3)
        self.assertEqual(labels[0].as_of_date, start_date)
        self.assertEqual(labels[0].horizon_days, 2)
        self.assertEqual(labels[0].forward_return_pct, Decimal("2.0000"))
        self.assertEqual(labels[0].benchmark_forward_return_pct, Decimal("2.0000"))
        self.assertEqual(labels[0].relative_return_pct, Decimal("0.0000"))
        self.assertLessEqual(labels[0].max_drawdown_pct, Decimal("0"))
        self.assertIsNotNone(labels[0].realized_volatility_pct)

    def test_compute_forward_labels_skips_incomplete_horizon(self) -> None:
        bars = [
            PriceBarPoint(date(2026, 1, 1), Decimal("100")),
            PriceBarPoint(date(2026, 1, 2), Decimal("101")),
        ]

        labels = compute_forward_labels(bars, horizons=[3])

        self.assertEqual(labels, [])

    def test_compute_price_feature_snapshots_uses_only_available_history(self) -> None:
        start_date = date(2025, 1, 1)
        bars = [
            PriceBarPoint(
                start_date + timedelta(days=index),
                Decimal("100") + Decimal(index) / Decimal("10"),
            )
            for index in range(230)
        ]

        snapshots = compute_price_feature_snapshots(bars)

        self.assertEqual(snapshots[0]["as_of_date"], start_date + timedelta(days=200))
        self.assertIn("return_21d_pct", snapshots[0]["features"])
        self.assertIn("realized_volatility_63d_pct", snapshots[0]["features"])
        self.assertEqual(snapshots[0]["quality_score"], Decimal("100.00"))

    def test_portfolio_fit_score_penalizes_downside_and_concentration(self) -> None:
        strong_fit = compute_portfolio_fit_score(
            expected_relative_return_pct=Decimal("5"),
            downside_p05_relative_return_pct=Decimal("-8"),
            confidence_score=Decimal("70"),
            concentration_after_pct=Decimal("8"),
            sector_exposure_after_pct=Decimal("20"),
        )
        weak_fit = compute_portfolio_fit_score(
            expected_relative_return_pct=Decimal("-2"),
            downside_p05_relative_return_pct=Decimal("-25"),
            confidence_score=Decimal("40"),
            concentration_after_pct=Decimal("30"),
            sector_exposure_after_pct=Decimal("45"),
        )

        self.assertGreater(strong_fit, weak_fit)
        self.assertGreaterEqual(strong_fit, Decimal("60"))
        self.assertLess(weak_fit, Decimal("50"))

    def test_latest_fundamental_features_use_as_of_date(self) -> None:
        snapshots = [
            TickerFeatureSnapshot(
                as_of_date=date(2026, 1, 1),
                feature_version="ticker_features_v1",
                features={"metrics": {"pe_ratio": "20", "net_margin_pct": "15"}},
            ),
            TickerFeatureSnapshot(
                as_of_date=date(2026, 3, 1),
                feature_version="ticker_features_v1",
                features={"metrics": {"pe_ratio": "25", "net_margin_pct": "18"}},
            ),
        ]

        features = _latest_fundamental_features_as_of(
            snapshots,
            as_of_date=date(2026, 2, 1),
        )

        self.assertEqual(features["pe_ratio"], "20")
        self.assertEqual(features["net_margin_pct"], "15")
