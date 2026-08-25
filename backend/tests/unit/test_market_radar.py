from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.market_constants import RADAR_WORKING_SET_SIZE
from app.main import app
from app.services.market_data.sessions import (
    JurisdictionSession,
    jurisdiction_for_ticker,
    partition_tickers,
    session_for,
)
from app.services.market_radar.catalog import CatalogSyncResult
from app.services.market_radar.scan import (
    _apply_scan_deltas,
    _quote_targets,
    _quote_usable_for_radar,
    _select_working_set,
    run_radar_scan,
)
from app.services.market_radar.priority import (
    assign_priorities,
    assign_priority,
    build_evidence_package,
    build_industry_contexts,
    is_auto_promotable,
    queue_priority_for,
    research_question_for,
    select_promotions,
    thesis_for,
)
from app.services.market_radar.scoring import RadarCandidate, is_flagged, score_candidate
from app.services.market_radar.watchlist import AlwaysWatchedSet


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class MarketRadarRouteTests(TestCase):
    def test_market_radar_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/market-radar/overview", paths)
        self.assertIn("get", paths["/api/market-radar/overview"])
        self.assertIn("/api/market-radar/scan", paths)
        self.assertIn("post", paths["/api/market-radar/scan"])
        self.assertIn("/api/market-radar/watchlist", paths)
        self.assertIn("get", paths["/api/market-radar/watchlist"])
        self.assertIn("post", paths["/api/market-radar/watchlist"])
        self.assertIn("/api/market-radar/watchlist/{ticker}", paths)
        self.assertIn("/api/market-radar/watchlist/{ticker}/chart", paths)


class JurisdictionSessionTests(TestCase):
    def test_us_open_during_regular_session(self) -> None:
        state = session_for("US", _utc(2026, 8, 11, 15, 0))
        self.assertTrue(state.is_open)
        self.assertTrue(state.allows_discovery)
        self.assertTrue(state.allows_live_quotes)

    def test_us_closed_overnight(self) -> None:
        state = session_for("US", _utc(2026, 8, 11, 3, 0))
        self.assertFalse(state.is_open)
        self.assertFalse(state.allows_discovery)
        self.assertFalse(state.allows_live_quotes)

    def test_us_post_close_allows_discovery_not_live_quotes(self) -> None:
        state = session_for("US", _utc(2026, 8, 11, 21, 30), post_close_hours=2)
        self.assertFalse(state.is_open)
        self.assertTrue(state.in_post_close_window)
        self.assertTrue(state.allows_discovery)
        self.assertFalse(state.allows_live_quotes)

    def test_us_closed_after_post_close_window(self) -> None:
        state = session_for("US", _utc(2026, 8, 11, 23, 30), post_close_hours=2)
        self.assertFalse(state.allows_discovery)

    def test_us_closed_on_weekend(self) -> None:
        state = session_for("US", _utc(2026, 8, 15, 15, 0))
        self.assertFalse(state.is_open)
        self.assertFalse(state.allows_discovery)

    def test_ngx_open_during_wat_session(self) -> None:
        # 10:00 WAT = 09:00 UTC
        state = session_for("NG", _utc(2026, 8, 11, 10, 0))
        self.assertTrue(state.is_open)
        self.assertTrue(state.allows_discovery)

    def test_ngx_closed_before_open(self) -> None:
        state = session_for("NG", _utc(2026, 8, 11, 8, 0))
        self.assertFalse(state.allows_discovery)

    def test_ngx_post_close_window(self) -> None:
        # NGX closes 14:30 WAT = 13:30 UTC
        state = session_for("NG", _utc(2026, 8, 11, 14, 0), post_close_hours=2)
        self.assertFalse(state.is_open)
        self.assertTrue(state.allows_discovery)
        self.assertFalse(state.allows_live_quotes)

    def test_ticker_partition_is_suffix_based(self) -> None:
        self.assertEqual(jurisdiction_for_ticker("AAPL"), "US")
        self.assertEqual(jurisdiction_for_ticker("gtco.ng"), "NG")
        grouped = partition_tickers(["AAPL", "MSFT", "GTCO.NG", "DANGCEM.NG"])
        self.assertEqual(grouped["US"], ["AAPL", "MSFT"])
        self.assertEqual(grouped["NG"], ["GTCO.NG", "DANGCEM.NG"])


class RadarScoringTests(TestCase):
    def test_volume_and_price_move_are_flagged(self) -> None:
        candidate = RadarCandidate(
            ticker="NVDA",
            name="NVIDIA",
            jurisdiction="US",
            change_pct=Decimal("6.2"),
            volume=5_000_000,
            avg_volume=1_000_000,
        )
        score_candidate(candidate)
        self.assertIn("price_move", candidate.flags)
        self.assertIn("unusual_volume", candidate.flags)
        self.assertTrue(is_flagged(candidate))
        self.assertGreaterEqual(candidate.anomaly_score, Decimal("8"))

    def test_small_move_is_not_flagged(self) -> None:
        candidate = RadarCandidate(
            ticker="XLU",
            name="Utilities",
            jurisdiction="US",
            change_pct=Decimal("0.4"),
            volume=1000,
            avg_volume=1000,
        )
        score_candidate(candidate)
        self.assertFalse(is_flagged(candidate))

    def test_discovery_list_flags_are_kept(self) -> None:
        candidate = RadarCandidate(
            ticker="XYZ",
            name="XYZ",
            jurisdiction="US",
            change_pct=Decimal("1.0"),
            flags=["unusual_volume"],
        )
        score_candidate(candidate)
        self.assertIn("unusual_volume", candidate.flags)
        self.assertFalse(is_flagged(candidate))
        self.assertEqual(candidate.anomaly_score, Decimal("0.00"))

    def test_universe_three_percent_is_not_flagged(self) -> None:
        candidate = RadarCandidate(
            ticker="XYZ",
            name="XYZ",
            jurisdiction="US",
            change_pct=Decimal("3.1"),
        )
        score_candidate(candidate)
        self.assertFalse(is_flagged(candidate))
        self.assertEqual(candidate.care_tier, "universe")
        self.assertNotIn("watched_move", candidate.flags)

    def test_watchlist_three_percent_is_flagged(self) -> None:
        candidate = RadarCandidate(
            ticker="AAPL",
            name="Apple",
            jurisdiction="US",
            on_watchlist=True,
            change_pct=Decimal("3.1"),
        )
        score_candidate(candidate)
        self.assertTrue(is_flagged(candidate))
        self.assertEqual(candidate.care_tier, "watchlist")
        self.assertIn("watched_move", candidate.flags)

    def test_queue_name_uses_watchlist_sensitivity(self) -> None:
        candidate = RadarCandidate(
            ticker="MSFT",
            name="Microsoft",
            jurisdiction="US",
            in_opportunity_queue=True,
            change_pct=Decimal("-2.6"),
        )
        score_candidate(candidate)
        self.assertTrue(is_flagged(candidate))
        self.assertEqual(candidate.care_tier, "queue")

    def test_position_two_percent_drop_is_flagged(self) -> None:
        candidate = RadarCandidate(
            ticker="GTCO.NG",
            name="GTCO",
            jurisdiction="NG",
            in_portfolio=True,
            change_pct=Decimal("-2.1"),
        )
        score_candidate(candidate)
        self.assertTrue(is_flagged(candidate))
        self.assertEqual(candidate.care_tier, "position")
        self.assertIn("position_risk", candidate.flags)

    def test_pulse_etf_three_percent_is_not_a_watchlist_alert(self) -> None:
        candidate = RadarCandidate(
            ticker="SPY",
            name="SPY",
            jurisdiction="US",
            always_watched=True,
            change_pct=Decimal("3.0"),
        )
        score_candidate(candidate)
        self.assertFalse(is_flagged(candidate))
        self.assertEqual(candidate.care_tier, "universe")
        self.assertNotIn("watched_move", candidate.flags)

    def test_evidence_driven_anomalies_are_flagged(self) -> None:
        candidate = RadarCandidate(
            ticker="MSFT",
            name="Microsoft",
            jurisdiction="US",
            change_pct=Decimal("1.8"),
            evidence={
                "price_return_zscore": "2.4",
                "volume_zscore": "2.1",
                "volatility_ratio": "1.7",
                "sector_relative_return_pct": "3.4",
                "sector_benchmark": "XLK",
            },
        )
        score_candidate(candidate)
        self.assertIn("price_anomaly", candidate.flags)
        self.assertIn("volume_anomaly", candidate.flags)
        self.assertIn("volatility_shift", candidate.flags)
        self.assertIn("sector_relative_move", candidate.flags)
        self.assertTrue(is_flagged(candidate))

    def test_sector_relative_uses_sector_etf_not_peer_average(self) -> None:
        from app.services.market_radar.scan import _apply_sector_relative

        xlk = RadarCandidate(
            ticker="XLK",
            name="Technology Select",
            jurisdiction="US",
            sector="Technology",
            asset_class="etf",
            change_pct=Decimal("1.0"),
        )
        aapl = RadarCandidate(
            ticker="AAPL",
            name="Apple",
            jurisdiction="US",
            sector="Technology",
            change_pct=Decimal("4.5"),
        )
        msft = RadarCandidate(
            ticker="MSFT",
            name="Microsoft",
            jurisdiction="US",
            sector="Technology",
            change_pct=Decimal("1.2"),
        )
        _apply_sector_relative([xlk, aapl, msft])
        self.assertEqual(aapl.evidence["sector_benchmark"], "XLK")
        self.assertEqual(aapl.evidence["sector_relative_return_pct"], "3.50")
        self.assertEqual(msft.evidence["sector_relative_return_pct"], "0.20")

    def test_working_set_keeps_always_watched_first(self) -> None:
        watched = [
            RadarCandidate(
                ticker=f"ETF{index}",
                name=f"ETF{index}",
                jurisdiction="US",
                always_watched=True,
            )
            for index in range(5)
        ]
        movers = [
            RadarCandidate(
                ticker=f"M{index}",
                name=f"M{index}",
                jurisdiction="US",
                anomaly_score=Decimal(index),
            )
            for index in range(120)
        ]
        working = _select_working_set(watched + movers)
        self.assertEqual(len(working), RADAR_WORKING_SET_SIZE)
        self.assertTrue(all(item.always_watched for item in working[:5]))
        self.assertEqual(working[5].ticker, "M119")

    def test_working_set_keeps_pinned_after_always_watched(self) -> None:
        always = RadarCandidate(
            ticker="SPY",
            name="SPY",
            jurisdiction="US",
            always_watched=True,
        )
        pinned = RadarCandidate(
            ticker="ZTG",
            name="ZTG",
            jurisdiction="US",
            pinned_prior=True,
            anomaly_score=Decimal("0"),
        )
        movers = [
            RadarCandidate(
                ticker=f"M{index}",
                name=f"M{index}",
                jurisdiction="US",
                anomaly_score=Decimal(index),
            )
            for index in range(10)
        ]
        working = _select_working_set([*movers, pinned, always])
        self.assertEqual(working[0].ticker, "SPY")
        self.assertEqual(working[1].ticker, "ZTG")
        self.assertEqual(working[2].ticker, "M9")

    def test_scan_lurch_is_flagged_from_clock_three(self) -> None:
        candidate = RadarCandidate(
            ticker="ZTG",
            name="ZTG",
            jurisdiction="US",
            change_pct=Decimal("-44"),
            evidence={"scan_delta_change_pct": "22"},
        )
        score_candidate(candidate)
        self.assertIn("scan_lurch", candidate.flags)
        self.assertTrue(is_flagged(candidate))

    def test_scan_deltas_measure_lurch_not_the_day_move(self) -> None:
        now = _utc(2026, 8, 17, 16, 0)
        candidate = RadarCandidate(
            ticker="ZTG",
            name="ZTG",
            jurisdiction="US",
            price=Decimal("1.20"),
            change_pct=Decimal("-44"),
            source_as_of=now,
            evidence={
                "prior_scan_price": "0.80",
                "prior_scan_change_pct": "-66",
                "prior_scan_as_of": "2026-08-17T15:00:00+00:00",
            },
        )
        _apply_scan_deltas([candidate])
        self.assertEqual(candidate.evidence["scan_delta_change_pct"], "22.00")
        self.assertEqual(candidate.evidence["scan_delta_price_pct"], "50.00")
        self.assertEqual(candidate.evidence["scan_state"], "rebounding")
        self.assertEqual(candidate.evidence["scan_minutes_since_prior"], 60)

    def test_scan_deltas_do_not_invent_jumps_on_carry_forward(self) -> None:
        candidate = RadarCandidate(
            ticker="ZTG",
            name="ZTG",
            jurisdiction="US",
            price=Decimal("1.20"),
            change_pct=Decimal("-44"),
            carried_forward=True,
            source_as_of=_utc(2026, 8, 17, 16, 0),
            evidence={
                "prior_scan_price": "0.80",
                "prior_scan_change_pct": "-66",
                "prior_scan_as_of": "2026-08-17T15:00:00+00:00",
            },
        )
        _apply_scan_deltas([candidate])
        self.assertNotIn("scan_delta_change_pct", candidate.evidence)

    def test_watchlist_quotes_ignore_same_day_stale_cache(self) -> None:
        quote = MagicMock()
        quote.is_stale = False
        quote.as_of = _utc(2026, 8, 17, 14, 0)
        now = _utc(2026, 8, 17, 16, 0)
        watched = RadarCandidate(
            ticker="ZTG",
            name="ZTG",
            jurisdiction="US",
            on_watchlist=True,
        )
        ordinary = RadarCandidate(
            ticker="AAPL",
            name="Apple",
            jurisdiction="US",
        )
        self.assertFalse(_quote_usable_for_radar(quote, now, candidate=watched))
        self.assertTrue(_quote_usable_for_radar(quote, now, candidate=ordinary))

    def test_quote_targets_are_capped_and_prioritize_watched_names(self) -> None:
        watched = RadarCandidate(
            ticker="GTCO.NG",
            name="GTCO",
            jurisdiction="NG",
            always_watched=True,
            is_catalog_member=True,
            evidence={"liquidity_rank": 99},
        )
        catalog = [
            RadarCandidate(
                ticker=f"CAT{index}.NG",
                name=f"CAT{index}",
                jurisdiction="NG",
                is_catalog_member=True,
                evidence={"liquidity_rank": index},
            )
            for index in range(20)
        ]

        targets = _quote_targets([*catalog, watched], "NG")

        self.assertEqual(targets[0], "GTCO.NG")
        self.assertLess(len(targets), len(catalog) + 1)


class RadarScanVendorGateTests(IsolatedAsyncioTestCase):
    def _session(self) -> AsyncMock:
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.scalars = AsyncMock(return_value=[])
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()
        return session

    def _scan_stack(self, *extra_patches):
        stack = ExitStack()
        stack.enter_context(
            patch(
                "app.services.market_radar.scan.sync_monitored_universe",
                new_callable=AsyncMock,
                return_value=CatalogSyncResult(0, 0, 0, 0),
            )
        )
        stack.enter_context(
            patch(
                "app.services.market_radar.scan.load_catalog_candidates",
                new_callable=AsyncMock,
                return_value=[],
            )
        )
        stack.enter_context(
            patch(
                "app.services.market_radar.scan._apply_cached_quotes",
                new_callable=AsyncMock,
                return_value=0,
            )
        )
        stack.enter_context(
            patch(
                "app.services.market_radar.scan._persist_vendor_tapes",
                new_callable=AsyncMock,
                return_value=0,
            )
        )
        stack.enter_context(
            patch(
                "app.services.market_radar.scan._apply_historical_evidence",
                new_callable=AsyncMock,
            )
        )
        stack.enter_context(
            patch(
                "app.services.market_radar.scan._pin_prior_working_set",
                new_callable=AsyncMock,
            )
        )
        stack.enter_context(
            patch(
                "app.services.market_radar.scan._annotate_queue_tape_moves",
                new_callable=AsyncMock,
                return_value=0,
            )
        )
        for extra in extra_patches:
            stack.enter_context(extra)
        return stack

    async def test_closed_markets_make_zero_vendor_calls(self) -> None:
        closed = {
            "US": JurisdictionSession("US", False, False, "US closed"),
            "NG": JurisdictionSession("NG", False, False, "NGX closed"),
        }
        session = self._session()
        with self._scan_stack():
            with (
            patch(
                "app.services.market_radar.scan.session_for",
                side_effect=lambda jurisdiction, now, **kwargs: closed[jurisdiction],
            ),
            patch(
                "app.services.market_radar.scan.load_always_watched",
                new_callable=AsyncMock,
                return_value=AlwaysWatchedSet(candidates={}),
            ),
            patch(
                "app.services.market_radar.scan.fetch_us_movers",
                new_callable=AsyncMock,
            ) as fetch_us,
            patch(
                "app.services.market_radar.scan.fetch_ngn_discovery",
                new_callable=AsyncMock,
            ) as fetch_ng,
            patch(
                "app.services.market_radar.scan.fetch_quotes",
                new_callable=AsyncMock,
            ) as fetch_quotes,
            patch(
                "app.services.market_radar.scan.record_system_log",
                new_callable=AsyncMock,
            ),
        ):
                run = await run_radar_scan(session)

        fetch_us.assert_not_awaited()
        fetch_ng.assert_not_awaited()
        fetch_quotes.assert_not_awaited()
        self.assertEqual(run.vendor_calls, 0)
        self.assertEqual(run.jurisdictions_scanned, [])
        self.assertEqual(len(run.jurisdictions_skipped), 2)
        self.assertEqual(run.status, "completed")

    async def test_open_ngx_does_not_call_us_vendors(self) -> None:
        states = {
            "US": JurisdictionSession("US", False, False, "US closed"),
            "NG": JurisdictionSession("NG", True, False, "NGX open"),
        }
        session = self._session()
        watched = AlwaysWatchedSet(
            candidates={
                "GTCO.NG": RadarCandidate(
                    ticker="GTCO.NG",
                    name="GTCO",
                    jurisdiction="NG",
                    always_watched=True,
                )
            }
        )
        discovered = RadarCandidate(
            ticker="DANGCEM.NG",
            name="Dangote Cement",
            jurisdiction="NG",
            source="ngnmarket",
        )
        with self._scan_stack():
            with (
            patch(
                "app.services.market_radar.scan.session_for",
                side_effect=lambda jurisdiction, now, **kwargs: states[jurisdiction],
            ),
            patch(
                "app.services.market_radar.scan.load_always_watched",
                new_callable=AsyncMock,
                return_value=watched,
            ),
            patch(
                "app.services.market_radar.scan.fetch_us_movers",
                new_callable=AsyncMock,
            ) as fetch_us,
            patch(
                "app.services.market_radar.scan.fetch_ngn_discovery",
                new_callable=AsyncMock,
                return_value=([discovered], 2, []),
            ) as fetch_ng,
            patch(
                "app.services.market_radar.scan.fetch_quotes",
                new_callable=AsyncMock,
                return_value={},
            ) as fetch_quotes,
            patch(
                "app.services.market_radar.scan.record_system_log",
                new_callable=AsyncMock,
            ),
        ):
                run = await run_radar_scan(session)

        fetch_us.assert_not_awaited()
        fetch_ng.assert_awaited_once()
        fetch_quotes.assert_awaited_once()
        self.assertEqual(fetch_quotes.await_args.args[0], ["GTCO.NG"])
        self.assertEqual(run.jurisdictions_scanned, ["NG"])
        self.assertEqual(run.vendor_calls, 3)

    async def test_force_scan_calls_vendors_when_closed(self) -> None:
        closed = {
            "US": JurisdictionSession("US", False, False, "US closed"),
            "NG": JurisdictionSession("NG", False, False, "NGX closed"),
        }
        session = self._session()
        with self._scan_stack():
            with (
            patch(
                "app.services.market_radar.scan.session_for",
                side_effect=lambda jurisdiction, now, **kwargs: closed[jurisdiction],
            ),
            patch(
                "app.services.market_radar.scan.load_always_watched",
                new_callable=AsyncMock,
                return_value=AlwaysWatchedSet(candidates={}),
            ),
            patch(
                "app.services.market_radar.scan.fetch_us_movers",
                new_callable=AsyncMock,
                return_value=([], 3, []),
            ) as fetch_us,
            patch(
                "app.services.market_radar.scan.fetch_ngn_discovery",
                new_callable=AsyncMock,
                return_value=([], 2, []),
            ) as fetch_ng,
            patch(
                "app.services.market_radar.scan.fetch_quotes",
                new_callable=AsyncMock,
            ) as fetch_quotes,
            patch(
                "app.services.market_radar.scan.record_system_log",
                new_callable=AsyncMock,
            ),
        ):
                run = await run_radar_scan(session, force=True, jurisdictions=["US", "NG"])

        fetch_us.assert_awaited_once()
        fetch_ng.assert_awaited_once()
        fetch_quotes.assert_not_awaited()
        self.assertEqual(run.jurisdictions_scanned, ["US", "NG"])
        self.assertEqual(run.vendor_calls, 5)

    async def test_manual_scan_promotes_only_to_the_scanning_user(self) -> None:
        states = {
            "US": JurisdictionSession("US", True, False, "US open"),
            "NG": JurisdictionSession("NG", False, False, "NGX closed"),
        }
        session = self._session()
        watched = AlwaysWatchedSet(
            candidates={
                "MSFT": RadarCandidate(
                    ticker="MSFT",
                    name="Microsoft",
                    jurisdiction="US",
                    always_watched=True,
                    in_portfolio=True,
                    price=Decimal("420"),
                    change_pct=Decimal("-6.2"),
                    volume=8_000_000,
                    avg_volume=2_000_000,
                    evidence={
                        "price_return_zscore": "-2.8",
                        "volume_zscore": "2.4",
                    },
                )
            }
        )
        with self._scan_stack():
            with (
            patch(
                "app.services.market_radar.scan.session_for",
                side_effect=lambda jurisdiction, now, **kwargs: states[jurisdiction],
            ),
            patch(
                "app.services.market_radar.scan.load_always_watched",
                new_callable=AsyncMock,
                return_value=watched,
            ),
            patch(
                "app.services.market_radar.scan.fetch_us_movers",
                new_callable=AsyncMock,
                return_value=([], 3, []),
            ),
            patch(
                "app.services.market_radar.scan.fetch_ngn_discovery",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.market_radar.scan.fetch_quotes",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "app.services.market_radar.scan.promote_flagged_candidates",
                new_callable=AsyncMock,
                return_value=1,
            ) as promote,
            patch(
                "app.services.market_radar.scan.record_system_log",
                new_callable=AsyncMock,
            ),
        ):
                run = await run_radar_scan(session, triggered_by_user_id="trigger-user")

        promote.assert_awaited_once()
        self.assertEqual(promote.await_args.kwargs["owner_ids"], ["trigger-user"])
        self.assertEqual(run.promotion_owner_ids, ["trigger-user"])
        promoted = promote.await_args.args[1]
        self.assertTrue(all(item.radar_priority in {"P0", "P1"} for item in promoted))


class RadarPriorityTests(TestCase):
    def test_portfolio_drawdown_is_p0_and_promotable(self) -> None:
        candidate = RadarCandidate(
            ticker="GTCO.NG",
            name="GTCO",
            jurisdiction="NG",
            industry="Banks",
            in_portfolio=True,
            change_pct=Decimal("-6.4"),
            volume=4_000_000,
            avg_volume=1_200_000,
            evidence={"price_return_zscore": "-2.6", "volume_zscore": "2.1"},
        )
        score_candidate(candidate)
        assign_priority(candidate)
        self.assertEqual(candidate.radar_priority, "P0")
        self.assertTrue(is_auto_promotable(candidate))
        self.assertEqual(queue_priority_for(candidate.radar_priority), "urgent")
        package = build_evidence_package(candidate)
        self.assertEqual(package["source"], "market_radar")
        self.assertEqual(package["radar_priority"], "P0")
        self.assertIn("GTCO.NG", thesis_for(candidate))
        self.assertTrue(package["facts"]["price_return_zscore"])

    def test_confirmed_anomaly_is_p1(self) -> None:
        candidate = RadarCandidate(
            ticker="AAPL",
            name="Apple",
            jurisdiction="US",
            sector="Technology",
            change_pct=Decimal("4.2"),
            volume=90_000_000,
            avg_volume=30_000_000,
            evidence={
                "price_return_zscore": "3.1",
                "volume_zscore": "2.6",
                "sector_relative_return_pct": "3.8",
                "sector_benchmark": "XLK",
                "avg_dollar_volume": "4000000000",
            },
        )
        score_candidate(candidate)
        assign_priority(candidate)
        self.assertEqual(candidate.radar_priority, "P1")
        self.assertTrue(is_auto_promotable(candidate))

    def test_raw_five_percent_move_is_not_auto_promoted(self) -> None:
        candidate = RadarCandidate(
            ticker="XYZ",
            name="XYZ",
            jurisdiction="US",
            change_pct=Decimal("5.2"),
            volume=1000,
            avg_volume=900,
        )
        score_candidate(candidate)
        assign_priority(candidate)
        self.assertTrue(is_flagged(candidate))
        self.assertIn(candidate.radar_priority, {"P2", "P3"})
        self.assertFalse(is_auto_promotable(candidate))

    def test_pulse_etf_is_never_auto_promoted(self) -> None:
        candidate = RadarCandidate(
            ticker="XLF",
            name="Financials Select",
            jurisdiction="US",
            asset_class="etf",
            always_watched=True,
            change_pct=Decimal("-6.0"),
            volume=20_000_000,
            avg_volume=8_000_000,
            evidence={"price_return_zscore": "-3.4", "volume_zscore": "2.8"},
        )
        score_candidate(candidate)
        assign_priority(candidate)
        self.assertTrue(is_flagged(candidate))
        self.assertFalse(is_auto_promotable(candidate))

    def test_select_promotions_keeps_all_p0_and_caps_p1(self) -> None:
        names = []
        for index in range(3):
            item = RadarCandidate(
                ticker=f"HOLD{index}",
                name=f"Hold {index}",
                jurisdiction="US",
                in_portfolio=True,
                change_pct=Decimal("-7.0"),
                evidence={"price_return_zscore": "-3.0", "volume_zscore": "2.2"},
            )
            score_candidate(item)
            assign_priority(item)
            names.append(item)
        for index in range(8):
            item = RadarCandidate(
                ticker=f"NEW{index}",
                name=f"New {index}",
                jurisdiction="US",
                change_pct=Decimal("4.5"),
                volume=9_000_000,
                avg_volume=2_000_000,
                evidence={
                    "price_return_zscore": "3.0",
                    "volume_zscore": "2.5",
                    "sector_relative_return_pct": "4.0",
                    "avg_dollar_volume": "250000000",
                },
            )
            score_candidate(item)
            assign_priority(item)
            names.append(item)
        noise = RadarCandidate(
            ticker="NOISE",
            name="Noise",
            jurisdiction="US",
            change_pct=Decimal("5.1"),
        )
        score_candidate(noise)
        assign_priority(noise)
        names.append(noise)

        selected = select_promotions(names, p1_limit=5)
        self.assertTrue(all(item.radar_priority in {"P0", "P1"} for item in selected))
        self.assertEqual(sum(1 for item in selected if item.radar_priority == "P0"), 3)
        self.assertLessEqual(sum(1 for item in selected if item.radar_priority == "P1"), 5)
        self.assertNotIn("NOISE", {item.ticker for item in selected})

    def test_watchlist_sensitive_flag_is_not_auto_promoted(self) -> None:
        candidate = RadarCandidate(
            ticker="AAPL",
            name="Apple",
            jurisdiction="US",
            on_watchlist=True,
            change_pct=Decimal("3.0"),
        )
        score_candidate(candidate)
        assign_priority(candidate)
        self.assertTrue(is_flagged(candidate))
        self.assertIn(candidate.radar_priority, {"P2", "P3"})
        self.assertFalse(is_auto_promotable(candidate))

    def test_position_small_drop_flags_but_is_not_p0(self) -> None:
        candidate = RadarCandidate(
            ticker="GTCO.NG",
            name="GTCO",
            jurisdiction="NG",
            in_portfolio=True,
            change_pct=Decimal("-2.1"),
        )
        score_candidate(candidate)
        assign_priority(candidate)
        self.assertTrue(is_flagged(candidate))
        self.assertNotEqual(candidate.radar_priority, "P0")
        self.assertFalse(is_auto_promotable(candidate))
        package = build_evidence_package(candidate)
        self.assertEqual(package["context"]["care_tier"], "position")


def _tape_name(
    ticker: str,
    industry: str,
    *,
    flagged: bool,
    jurisdiction: str = "US",
) -> RadarCandidate:
    candidate = RadarCandidate(
        ticker=ticker,
        name=ticker,
        jurisdiction=jurisdiction,
        industry=industry,
        sector=industry,
        change_pct=Decimal("-5.4") if flagged else Decimal("0.2"),
        volume=5_000_000 if flagged else 800_000,
        avg_volume=1_200_000,
        evidence=(
            {
                "price_return_zscore": "-2.4",
                "volume_zscore": "2.2",
                "avg_dollar_volume": "9000000",
            }
            if flagged
            else {}
        ),
    )
    score_candidate(candidate)
    return candidate


class MoveScopeTests(TestCase):
    def test_single_flagged_name_is_isolated(self) -> None:
        names = [
            _tape_name("JPM", "Banks", flagged=True),
            *[_tape_name(f"Q{index}", "Banks", flagged=False) for index in range(5)],
        ]
        assign_priorities(names)
        self.assertEqual(names[0].evidence["move_scope"], "isolated")
        contexts = build_industry_contexts(names)
        status = next(iter(contexts.values())).status
        self.assertEqual(status, "isolated_names")
        self.assertIn("company-specific", research_question_for(names[0]))

    def test_broad_industry_tape_is_industry_event(self) -> None:
        names = [
            *[_tape_name(f"B{index}", "Banks", flagged=True) for index in range(4)],
            *[_tape_name(f"Q{index}", "Banks", flagged=False) for index in range(4)],
        ]
        assign_priorities(names)
        self.assertEqual(names[0].evidence["move_scope"], "industry")
        contexts = build_industry_contexts(names)
        self.assertEqual(next(iter(contexts.values())).status, "industry_event")
        self.assertIn("riding a Banks move", research_question_for(names[0]))

    def test_several_hot_industries_are_a_market_event(self) -> None:
        names = [
            *[_tape_name(f"B{index}", "Banks", flagged=True) for index in range(4)],
            *[_tape_name(f"BQ{index}", "Banks", flagged=False) for index in range(4)],
            *[_tape_name(f"E{index}", "Energy", flagged=True) for index in range(4)],
            *[_tape_name(f"EQ{index}", "Energy", flagged=False) for index in range(4)],
        ]
        assign_priorities(names)
        self.assertEqual(names[0].evidence["move_scope"], "market")
        statuses = {item.status for item in build_industry_contexts(names).values()}
        self.assertEqual(statuses, {"market_event"})
        self.assertIn("market-wide", research_question_for(names[0]))

    def test_pulse_etf_does_not_create_an_industry_event(self) -> None:
        names = [
            RadarCandidate(
                ticker="XLF",
                name="Financials",
                jurisdiction="US",
                industry="Banks",
                sector="Banks",
                asset_class="etf",
                always_watched=True,
                change_pct=Decimal("-6.0"),
                volume=20_000_000,
                avg_volume=8_000_000,
                evidence={"price_return_zscore": "-3.4", "volume_zscore": "2.8"},
            ),
            *[_tape_name(f"Q{index}", "Banks", flagged=False) for index in range(6)],
        ]
        score_candidate(names[0])
        assign_priorities(names)
        context = next(iter(build_industry_contexts(names).values()))
        self.assertEqual(context.flagged_count, 0)
        self.assertEqual(context.status, "quiet")
        self.assertEqual(names[0].evidence["move_scope"], "none")


