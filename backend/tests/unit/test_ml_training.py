from datetime import date, timedelta
from decimal import Decimal
from unittest import TestCase

from app.services.ticker_intelligence.ml_training import (
    PriceBarPoint,
    compute_forward_labels,
)


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
