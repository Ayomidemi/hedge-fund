from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from app.api.schemas.operating_core import (
    InstrumentResponse,
    TradeJournalEntryResponse,
)
from app.services.portfolio.operating_core import _trade_journal_summary


class TradeJournalTests(TestCase):
    def test_trade_journal_summary_aggregates_execution_metrics(self) -> None:
        instrument = InstrumentResponse(
            id=uuid4(),
            ticker="AAPL",
            name="Apple Inc.",
            asset_class="equity",
            exchange="XNAS",
            currency="USD",
            sector="Technology",
            industry="Consumer Electronics",
        )
        trade_time = datetime(2026, 8, 11, tzinfo=timezone.utc)

        summary = _trade_journal_summary(
            [
                TradeJournalEntryResponse(
                    id=uuid4(),
                    instrument=instrument,
                    trade_date=trade_time,
                    side="buy",
                    status="filled",
                    quantity=Decimal("2"),
                    executed_price=Decimal("100"),
                    fees=Decimal("1"),
                    rationale="Entry",
                    risk_notes=None,
                    broker_reference=None,
                    notional_value=Decimal("200"),
                    cash_impact=Decimal("-201"),
                    fee_bps=Decimal("50"),
                    has_risk_notes=False,
                ),
                TradeJournalEntryResponse(
                    id=uuid4(),
                    instrument=instrument,
                    trade_date=trade_time,
                    side="sell",
                    status="filled",
                    quantity=Decimal("1"),
                    executed_price=Decimal("110"),
                    fees=Decimal("0.55"),
                    rationale="Trim",
                    risk_notes="Reduce exposure.",
                    broker_reference="T-1",
                    notional_value=Decimal("110"),
                    cash_impact=Decimal("109.45"),
                    fee_bps=Decimal("50"),
                    has_risk_notes=True,
                ),
            ]
        )

        self.assertEqual(summary.total_trades, 2)
        self.assertEqual(summary.buy_count, 1)
        self.assertEqual(summary.sell_count, 1)
        self.assertEqual(summary.unique_tickers, 1)
        self.assertEqual(summary.gross_traded_value, Decimal("310.00"))
        self.assertEqual(summary.net_cash_impact, Decimal("-91.55"))
        self.assertEqual(summary.total_fees, Decimal("1.55"))
        self.assertEqual(summary.average_fee_bps, Decimal("50.00"))
        self.assertEqual(summary.last_trade_at, trade_time)
