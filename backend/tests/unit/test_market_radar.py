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
    _quote_targets,
    _select_working_set,
    run_radar_scan,
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
                    price=Decimal("420"),
                    change_pct=Decimal("7.5"),
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

