from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from app.api.schemas.operating_core import (
    InstrumentResponse,
    TradeJournalEntryResponse,
)
from app.services.portfolio.operating_core import (
    _trade_cash_ledger_values,
    _trade_journal_summary,
    _trade_source_reference,
)


def _portfolio():
    return type("PortfolioLike", (), {"base_currency": "USD"})()


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
                    fees_in_base=Decimal("1"),
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
                    fees_in_base=Decimal("0.55"),
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

    def test_trade_cash_ledger_values_include_stable_trade_reference(self) -> None:
        trade_id = uuid4()
        instrument = InstrumentResponse(
            id=uuid4(),
            ticker="SPY",
            name="SPDR S&P 500 ETF Trust",
            asset_class="etf",
            exchange="ARCX",
            currency="USD",
            sector="Broad Market",
            industry=None,
        )
        trade_time = datetime(2026, 8, 11, tzinfo=timezone.utc)
        trade = type(
            "TradeLike",
            (),
            {
                "id": trade_id,
                "trade_date": trade_time,
                "side": "buy",
                "quantity": Decimal("2"),
                "executed_price": Decimal("100"),
                "fees": Decimal("1.25"),
                "broker_reference": "IBKR",
            },
        )()

        values = _trade_cash_ledger_values(trade, instrument, _portfolio(), {})

        self.assertEqual(values["entry_date"], trade_time.date())
        self.assertEqual(values["amount"], Decimal("-201.25"))
        self.assertEqual(values["currency"], "USD")
        self.assertEqual(values["entry_type"], "trade_buy")
        self.assertEqual(values["platform"], "IBKR")
        self.assertEqual(values["description"], "BUY 2 SPY @ 100")
        self.assertEqual(values["source_reference"], _trade_source_reference(trade_id))

    def test_sell_trade_cash_ledger_values_are_positive_less_fees(self) -> None:
        trade_id = uuid4()
        instrument = InstrumentResponse(
            id=uuid4(),
            ticker="SPY",
            name="SPDR S&P 500 ETF Trust",
            asset_class="etf",
            exchange="ARCX",
            currency="USD",
            sector="Broad Market",
            industry=None,
        )
        trade = type(
            "TradeLike",
            (),
            {
                "id": trade_id,
                "trade_date": datetime(2026, 8, 11, tzinfo=timezone.utc),
                "side": "sell",
                "quantity": Decimal("1"),
                "executed_price": Decimal("110"),
                "fees": Decimal("0.55"),
                "broker_reference": None,
            },
        )()

        values = _trade_cash_ledger_values(trade, instrument, _portfolio(), {})

        self.assertEqual(values["amount"], Decimal("109.45"))
        self.assertEqual(values["entry_type"], "trade_sell")
        self.assertEqual(values["platform"], "manual")
