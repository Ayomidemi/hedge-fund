from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4

from app.services.attribution.performance import _accumulate_trade_attribution
from app.services.reporting.monthly import (
    _research_summary,
    _resolve_period,
    _snapshot_response,
)


class MonthlyReportingTests(TestCase):
    def test_research_summary_reads_action_from_memo_scores(self) -> None:
        rows = _research_summary(
            [
                SimpleNamespace(
                    classification="investment_candidate",
                    scores={"action": "buy_candidate"},
                ),
                SimpleNamespace(
                    classification="investment_candidate",
                    scores={"action": "buy_candidate"},
                ),
                SimpleNamespace(
                    classification="watch",
                    scores={},
                ),
            ]
        )

        values = {row.label: row.value for row in rows}

        self.assertEqual(values["Investment Candidate memos"], "2")
        self.assertEqual(values["Buy Candidate actions"], "2")
        self.assertEqual(values["No Action actions"], "1")

    def test_quarterly_period_uses_selected_quarter(self) -> None:
        period = _resolve_period(
            "quarterly",
            year=2026,
            month=None,
            quarter=2,
            as_of=None,
        )

        self.assertEqual(period.key, "2026-Q2")
        self.assertEqual(period.label, "Q2 2026")
        self.assertEqual(period.start.isoformat(), "2026-04-01")
        self.assertEqual(period.end_exclusive.isoformat(), "2026-07-01")

    def test_weekly_period_starts_on_monday(self) -> None:
        period = _resolve_period(
            "weekly",
            year=None,
            month=None,
            quarter=None,
            as_of=date(2026, 8, 26),
        )

        self.assertEqual(period.start.isoformat(), "2026-08-24")
        self.assertEqual(period.end_exclusive.isoformat(), "2026-08-31")

    def test_period_attribution_seeds_pre_period_cost_basis(self) -> None:
        instrument_id = uuid4()
        instrument = SimpleNamespace(
            id=instrument_id,
            ticker="AAPL",
            name="Apple Inc.",
            asset_class="equity",
            exchange="NASDAQ",
            currency="USD",
            sector="Technology",
            industry="Consumer Electronics",
        )
        trades = [
            SimpleNamespace(
                id=uuid4(),
                instrument_id=instrument_id,
                instrument=instrument,
                status="filled",
                executed_price=Decimal("100"),
                quantity=Decimal("10"),
                fees=Decimal("1"),
                side="buy",
                trade_date=datetime(2026, 7, 15, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=uuid4(),
                instrument_id=instrument_id,
                instrument=instrument,
                status="filled",
                executed_price=Decimal("120"),
                quantity=Decimal("4"),
                fees=Decimal("1"),
                side="sell",
                trade_date=datetime(2026, 8, 5, tzinfo=timezone.utc),
            ),
        ]

        accumulators, events, warnings = _accumulate_trade_attribution(
            trades,
            period_start=date(2026, 8, 1),
        )

        accumulator = accumulators[instrument_id]
        self.assertEqual(accumulator.trade_count, 1)
        self.assertEqual(accumulator.gross_buys, Decimal("0"))
        self.assertEqual(accumulator.gross_sells, Decimal("480.00"))
        self.assertEqual(accumulator.gross_realized_pnl, Decimal("80.00"))
        self.assertEqual(accumulator.fees, Decimal("1.00"))
        self.assertEqual(len(events), 1)
        self.assertEqual(warnings, [])

    def test_snapshot_response_can_omit_payload_for_archive_lists(self) -> None:
        snapshot = SimpleNamespace(
            id=uuid4(),
            report_kind="monthly",
            period_label="August 2026",
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            title="Pease Capital - August 2026 Monthly Investor Letter",
            nav=Decimal("1000"),
            return_pct=Decimal("2.5"),
            created_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            payload={"payload_version": 2, "period_key": "2026-08"},
        )

        response = _snapshot_response(snapshot, include_payload=False)

        self.assertIsNone(response.payload)
        self.assertEqual(response.payload_version, 2)
