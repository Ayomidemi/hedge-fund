from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.api.schemas.operating_core import InstrumentCreate
from app.api.schemas.ticker_intelligence import TickerMetricsInput, TickerPrefillResponse
from app.core.auth import AuthenticatedUser
from app.services.ticker_intelligence.verdict import create_ticker_triage
from app.services.ticker_intelligence.scoring import (
    action_from_score,
    recommended_weight_from_score,
    score_ticker,
)


class TickerIntelligenceScoringTests(TestCase):
    def test_strong_manual_metrics_create_candidate_score(self) -> None:
        scorecard = score_ticker(
            TickerMetricsInput(
                pe_ratio=Decimal("22"),
                forward_pe=Decimal("18"),
                revenue_growth_pct=Decimal("18"),
                earnings_growth_pct=Decimal("21"),
                free_cash_flow_yield_pct=Decimal("4.5"),
                net_margin_pct=Decimal("24"),
                debt_to_equity=Decimal("0.35"),
                price_vs_200d_pct=Decimal("14"),
                relative_strength_6m_pct=Decimal("11"),
                volatility_30d_pct=Decimal("24"),
            ),
            asset_class="equity",
        )

        self.assertGreaterEqual(scorecard.composite_score, Decimal("70"))
        self.assertGreaterEqual(scorecard.confidence_score, Decimal("80"))
        self.assertIsNotNone(scorecard.capital_score)
        self.assertGreaterEqual(scorecard.capital_score or Decimal("0"), Decimal("70"))
        self.assertIn(scorecard.action, {"buy", "hold"})
        self.assertGreater(scorecard.recommended_weight, Decimal("0"))

    def test_sparse_metrics_stay_on_watch_even_with_neutral_score(self) -> None:
        scorecard = score_ticker(
            TickerMetricsInput(pe_ratio=Decimal("18")),
            asset_class="equity",
        )

        self.assertEqual(scorecard.action, "watch")
        self.assertEqual(scorecard.classification, "data-incomplete watchlist")
        self.assertEqual(scorecard.recommended_weight, Decimal("0.0000"))
        self.assertLess(scorecard.capital_coverage, Decimal("40"))

    def test_missing_metrics_are_excluded_not_neutral_fifty(self) -> None:
        scorecard = score_ticker(
            TickerMetricsInput(
                pe_ratio=Decimal("12"),
                forward_pe=Decimal("11"),
                free_cash_flow_yield_pct=Decimal("6"),
                net_margin_pct=Decimal("20"),
                debt_to_equity=Decimal("0.3"),
                revenue_growth_pct=Decimal("15"),
                earnings_growth_pct=Decimal("18"),
                # No momentum fields — must not invent 50s into capital.
            ),
            asset_class="equity",
        )

        self.assertIsNotNone(scorecard.capital_score)
        self.assertIsNone(scorecard.timing_score)
        self.assertEqual(scorecard.timing_coverage, Decimal("0.00"))
        self.assertGreaterEqual(scorecard.capital_score or Decimal("0"), Decimal("70"))

    def test_crash_tape_hurts_timing_not_automatic_capital_avoid(self) -> None:
        scorecard = score_ticker(
            TickerMetricsInput(
                pe_ratio=Decimal("14"),
                forward_pe=Decimal("12"),
                revenue_growth_pct=Decimal("10"),
                earnings_growth_pct=Decimal("12"),
                free_cash_flow_yield_pct=Decimal("5"),
                net_margin_pct=Decimal("18"),
                debt_to_equity=Decimal("0.5"),
                price_vs_200d_pct=Decimal("-33"),
                relative_strength_6m_pct=Decimal("-28"),
                volatility_30d_pct=Decimal("70"),
            ),
            asset_class="equity",
        )

        self.assertIsNotNone(scorecard.capital_score)
        self.assertIsNotNone(scorecard.timing_score)
        self.assertGreaterEqual(scorecard.capital_score or Decimal("0"), Decimal("55"))
        self.assertLess(scorecard.timing_score or Decimal("100"), Decimal("35"))
        self.assertNotEqual(scorecard.action, "avoid")
        self.assertEqual(scorecard.hard_blockers, [])

    def test_extreme_leverage_is_hard_capital_blocker(self) -> None:
        scorecard = score_ticker(
            TickerMetricsInput(
                debt_to_equity=Decimal("7"),
                free_cash_flow_yield_pct=Decimal("-2"),
                net_margin_pct=Decimal("-5"),
                pe_ratio=Decimal("8"),
            ),
            asset_class="equity",
        )

        self.assertTrue(scorecard.hard_blockers)
        self.assertEqual(scorecard.action, "avoid")
        self.assertEqual(scorecard.recommended_weight, Decimal("0.0000"))

    def test_etf_weight_cap_is_larger_than_single_equity_cap(self) -> None:
        equity_weight = recommended_weight_from_score(
            Decimal("95"),
            Decimal("90"),
            "equity",
        )
        etf_weight = recommended_weight_from_score(
            Decimal("95"),
            Decimal("90"),
            "etf",
        )

        self.assertGreater(etf_weight, equity_weight)
        self.assertLessEqual(equity_weight, Decimal("0.0500"))
        self.assertLessEqual(etf_weight, Decimal("0.2000"))

    def test_low_known_capital_score_is_avoid_action(self) -> None:
        self.assertEqual(action_from_score(Decimal("30"), Decimal("90")), "avoid")


class TickerDeskTests(TestCase):
    def test_ticker_variants_cover_ngx_suffix(self) -> None:
        from app.services.ticker_intelligence.analysis import ticker_variants

        self.assertEqual(ticker_variants("dangcem.ng"), {"DANGCEM", "DANGCEM.NG"})
        self.assertEqual(ticker_variants("aapl"), {"AAPL", "AAPL.NG"})

    def test_decision_snapshot_turns_candidate_triage_into_research_candidate(self) -> None:
        from app.services.ticker_intelligence.analysis import _build_decision_snapshot

        snapshot = _build_decision_snapshot(
            latest_triage=SimpleNamespace(
                confidence_score=Decimal("65"),
                composite_score=Decimal("72"),
                generated_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
                next_action="Proceed to deep research.",
                recommended_weight=Decimal("0.0300"),
                triage_decision="candidate",
                context={
                    "capital_score": "74",
                    "timing_score": "60",
                    "capital_blocked": False,
                },
            ),
            position=None,
            opportunity=None,
            watchlist_id=None,
            radar_snapshot=None,
            radar_evidence={},
            pre_trade=None,
            news=None,
            memo_count=0,
        )

        self.assertEqual(snapshot.action, "research_candidate")
        self.assertEqual(snapshot.action_label, "Research Candidate")
        self.assertEqual(snapshot.stance, "constructive")

    def test_decision_snapshot_flags_owned_hard_pass_as_position_review(self) -> None:
        from app.services.ticker_intelligence.analysis import _build_decision_snapshot

        snapshot = _build_decision_snapshot(
            latest_triage=SimpleNamespace(
                confidence_score=Decimal("70"),
                composite_score=Decimal("35"),
                generated_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
                next_action="Hard pass on capital.",
                recommended_weight=Decimal("0.0000"),
                triage_decision="hard_pass",
                context={"capital_blocked": True, "hard_blockers": ["Extreme leverage."]},
            ),
            position=SimpleNamespace(quantity=Decimal("10")),
            opportunity=None,
            watchlist_id=None,
            radar_snapshot=None,
            radar_evidence={},
            pre_trade=None,
            news=None,
            memo_count=0,
        )

        self.assertEqual(snapshot.action, "review_position")
        self.assertEqual(snapshot.action_label, "Review Position")
        self.assertEqual(snapshot.stance, "risk")

    def test_decision_snapshot_maps_legacy_reject_to_hard_pass(self) -> None:
        from app.services.ticker_intelligence.analysis import _build_decision_snapshot

        snapshot = _build_decision_snapshot(
            latest_triage=SimpleNamespace(
                confidence_score=Decimal("70"),
                composite_score=Decimal("35"),
                generated_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
                next_action="Reject for now.",
                recommended_weight=Decimal("0.0000"),
                triage_decision="reject",
                context={},
            ),
            position=None,
            opportunity=None,
            watchlist_id=None,
            radar_snapshot=None,
            radar_evidence={},
            pre_trade=None,
            news=None,
            memo_count=0,
        )

        self.assertEqual(snapshot.action, "hard_pass")
        self.assertEqual(snapshot.action_label, "Hard Pass")

    def test_decision_snapshot_asks_for_triage_when_no_saved_screen_exists(self) -> None:
        from app.services.ticker_intelligence.analysis import _build_decision_snapshot

        snapshot = _build_decision_snapshot(
            latest_triage=None,
            position=None,
            opportunity=None,
            watchlist_id=None,
            radar_snapshot=None,
            radar_evidence={},
            pre_trade=None,
            news=None,
            memo_count=0,
        )

        self.assertEqual(snapshot.action, "run_triage")
        self.assertEqual(snapshot.action_label, "Run Quick Triage")


class TickerTriageTests(IsolatedAsyncioTestCase):
    async def test_create_ticker_triage_persists_screen_with_cached_price(self) -> None:
        session = FakeTriageSession()
        instrument = SimpleNamespace(id=uuid4(), ticker="AAPL")
        prefill = TickerPrefillResponse(
            instrument=InstrumentCreate(
                ticker="AAPL",
                name="Apple Inc.",
                asset_class="equity",
                exchange="XNAS",
                currency="USD",
                sector="Technology",
                industry="Consumer Electronics",
            ),
            metrics=TickerMetricsInput(
                current_price=Decimal("150.00"),
                market_cap_billion=Decimal("3000"),
                pe_ratio=Decimal("24"),
                forward_pe=Decimal("20"),
                revenue_growth_pct=Decimal("8"),
                earnings_growth_pct=Decimal("10"),
                free_cash_flow_yield_pct=Decimal("4.5"),
                net_margin_pct=Decimal("24"),
                debt_to_equity=Decimal("0.35"),
                price_vs_200d_pct=Decimal("6"),
                relative_strength_6m_pct=Decimal("8"),
                volatility_30d_pct=Decimal("22"),
            ),
            provider="test-provider",
            source_reference="test://aapl",
            data_timestamp=datetime(2026, 8, 24, tzinfo=timezone.utc),
            source_warnings=[],
            raw_sources={},
        )

        with (
            patch(
                "app.services.ticker_intelligence.verdict.prefill_ticker",
                new_callable=AsyncMock,
                return_value=prefill,
            ) as prefill_ticker,
            patch(
                "app.services.ticker_intelligence.verdict.upsert_instrument",
                new_callable=AsyncMock,
                return_value=instrument,
            ) as upsert_instrument,
            patch(
                "app.services.ticker_intelligence.verdict.get_cached_quote_price",
                new_callable=AsyncMock,
                return_value=Decimal("151.00"),
            ),
            patch(
                "app.services.ticker_intelligence.verdict.get_ticker_desk",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(
                    on_watchlist=False,
                    position=None,
                    opportunity=None,
                    radar=None,
                    news=None,
                    pre_trade=None,
                    memos=[],
                ),
            ),
            patch(
                "app.services.ticker_intelligence.verdict.record_system_log",
                new_callable=AsyncMock,
            ),
        ):
            response = await create_ticker_triage(
                session,
                "AAPL",
                market="US",
                user=AuthenticatedUser(id="user-1", email="pm@example.com"),
            )

        prefill_ticker.assert_awaited_once_with(
            "AAPL",
            market_hint="US",
            scope="triage",
        )
        upsert_instrument.assert_awaited_once()
        triage = next(
            item
            for item in session.added
            if item.__class__.__name__ == "TickerTriageRun"
        )
        self.assertTrue(session.committed)
        self.assertEqual(response.triage_run_id, triage.id)
        self.assertEqual(response.metrics.current_price, Decimal("151.00"))
        self.assertEqual(triage.metrics["current_price"], "151.00")
        self.assertEqual(triage.provider, "test-provider")
        self.assertIn(response.triage_decision, {"candidate", "research", "watch"})
        self.assertIsNotNone(response.entry_plan)
        self.assertIn("capital_score", triage.context)

    async def test_chase_spike_marks_setup_invalid(self) -> None:
        session = FakeTriageSession()
        instrument = SimpleNamespace(id=uuid4(), ticker="FOMO")
        prefill = TickerPrefillResponse(
            instrument=InstrumentCreate(
                ticker="FOMO",
                name="Fomo Corp",
                asset_class="equity",
                exchange="XNAS",
                currency="USD",
            ),
            metrics=TickerMetricsInput(
                current_price=Decimal("40"),
                pe_ratio=Decimal("20"),
                forward_pe=Decimal("18"),
                revenue_growth_pct=Decimal("12"),
                earnings_growth_pct=Decimal("14"),
                free_cash_flow_yield_pct=Decimal("3"),
                net_margin_pct=Decimal("15"),
                debt_to_equity=Decimal("0.6"),
                price_vs_200d_pct=Decimal("40"),
                relative_strength_6m_pct=Decimal("35"),
                volatility_30d_pct=Decimal("55"),
            ),
            provider="test-provider",
            source_reference="test://fomo",
            data_timestamp=datetime(2026, 8, 24, tzinfo=timezone.utc),
            source_warnings=[],
            raw_sources={},
        )

        with (
            patch(
                "app.services.ticker_intelligence.verdict.prefill_ticker",
                new_callable=AsyncMock,
                return_value=prefill,
            ),
            patch(
                "app.services.ticker_intelligence.verdict.upsert_instrument",
                new_callable=AsyncMock,
                return_value=instrument,
            ),
            patch(
                "app.services.ticker_intelligence.verdict.get_cached_quote_price",
                new_callable=AsyncMock,
                return_value=Decimal("40"),
            ),
            patch(
                "app.services.ticker_intelligence.verdict.get_ticker_desk",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(
                    on_watchlist=False,
                    position=None,
                    opportunity=None,
                    radar=SimpleNamespace(change_pct=Decimal("80"), scan_state="spiking"),
                    news=None,
                    pre_trade=None,
                    memos=[],
                ),
            ),
            patch(
                "app.services.ticker_intelligence.verdict.record_system_log",
                new_callable=AsyncMock,
            ),
        ):
            response = await create_ticker_triage(
                session,
                "FOMO",
                market="US",
                user=AuthenticatedUser(id="user-1", email="pm@example.com"),
            )

        self.assertEqual(response.triage_decision, "setup_invalid")
        self.assertTrue(response.capital_blocked)
        self.assertEqual(response.recommended_weight, Decimal("0.0000"))
        self.assertEqual(response.entry_plan.status if response.entry_plan else None, "invalid_chase")


class FakeTriageSession:
    def __init__(self) -> None:
        self.added = []
        self.flushed = 0
        self.committed = False

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed += 1
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    async def commit(self) -> None:
        self.committed = True
