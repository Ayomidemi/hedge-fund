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
from app.services.market_radar.scan import _select_working_set, run_radar_scan
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


class RadarScanVendorGateTests(IsolatedAsyncioTestCase):
    def _session(self) -> AsyncMock:
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.scalars = AsyncMock(return_value=[])
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()
        return session

    async def test_closed_markets_make_zero_vendor_calls(self) -> None:
        closed = {
            "US": JurisdictionSession("US", False, False, "US closed"),
            "NG": JurisdictionSession("NG", False, False, "NGX closed"),
        }
        session = self._session()
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
