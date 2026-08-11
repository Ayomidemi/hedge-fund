from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4

from app.main import app
from app.services.attribution.performance import (
    _accumulate_trade_attribution,
    _hit_rate,
    _profit_factor,
)


class AttributionTests(TestCase):
    def test_attribution_route_is_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/attribution/overview", paths)
        self.assertIn("get", paths["/api/attribution/overview"])

    def test_trade_attribution_tracks_realized_pnl_and_costs(self) -> None:
        instrument_id = uuid4()
        instrument = SimpleNamespace(
            id=instrument_id,
            ticker="AAPL",
            name="Apple Inc.",
            asset_class="equity",
            exchange="XNAS",
            currency="USD",
            sector="Technology",
            industry="Consumer Electronics",
        )
        first_trade_id = uuid4()
        second_trade_id = uuid4()
        trade_date = datetime(2026, 8, 11, tzinfo=timezone.utc)

        accumulators, events, warnings = _accumulate_trade_attribution(
            [
                SimpleNamespace(
                    id=first_trade_id,
                    instrument_id=instrument_id,
                    instrument=instrument,
                    trade_date=trade_date,
                    side="buy",
                    status="filled",
                    quantity=Decimal("2"),
                    executed_price=Decimal("100"),
                    fees=Decimal("1"),
                ),
                SimpleNamespace(
                    id=second_trade_id,
                    instrument_id=instrument_id,
                    instrument=instrument,
                    trade_date=trade_date,
                    side="sell",
                    status="filled",
                    quantity=Decimal("1"),
                    executed_price=Decimal("115"),
                    fees=Decimal("0.50"),
                ),
            ]
        )

        accumulator = accumulators[instrument_id]

        self.assertEqual(warnings, [])
        self.assertEqual(accumulator.gross_buys, Decimal("200.00"))
        self.assertEqual(accumulator.gross_sells, Decimal("115.00"))
        self.assertEqual(accumulator.gross_realized_pnl, Decimal("15.00"))
        self.assertEqual(accumulator.fees, Decimal("1.50"))
        self.assertEqual(accumulator.closed_trade_count, 1)
        self.assertEqual(accumulator.winning_trade_count, 1)
        self.assertEqual(events[0].net_realized_pnl, Decimal("14.50"))

    def test_hit_rate_and_profit_factor_handle_empty_denominators(self) -> None:
        self.assertIsNone(_hit_rate(0, 0))
        self.assertIsNone(_profit_factor(Decimal("10"), Decimal("0")))
        self.assertEqual(_hit_rate(2, 4), Decimal("50.00"))
        self.assertEqual(
            _profit_factor(Decimal("30"), Decimal("10")),
            Decimal("3.00"),
        )
