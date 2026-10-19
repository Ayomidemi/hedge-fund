import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes.market_radar import router
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.locks import JOB_LOCK_NAMESPACE, RADAR_SCAN_LOCK_KEY
from app.db.session import get_session
from app.services.market_radar.runner import RadarScanInProgress, run_locked_radar_scan
from app.workers.tasks.radar_scan import _run


class RadarScanRunnerTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.connection = SimpleNamespace(scalar=AsyncMock(return_value=True))
        self.lock_transaction = AsyncMock()
        self.lock_transaction.__aenter__.return_value = self.connection
        self.engine = SimpleNamespace(
            begin=MagicMock(return_value=self.lock_transaction),
            dispose=AsyncMock(),
        )
        self.session = SimpleNamespace(bind=self.engine, commit=AsyncMock())

    def api(self) -> FastAPI:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_session] = lambda: self.session
        app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUser(
            id="request-user", email=None
        )
        return app

    async def test_lock_survives_scan_commits_and_releases_after_success(self) -> None:
        run = object()

        async def scan(session, **kwargs):
            for _ in range(2):
                await session.commit()
                self.lock_transaction.__aexit__.assert_not_awaited()
            return run

        with patch("app.services.market_radar.runner.run_radar_scan", side_effect=scan):
            result = await run_locked_radar_scan(self.session)

        self.assertIs(result, run)
        self.assertEqual(self.session.commit.await_count, 2)
        self.lock_transaction.__aexit__.assert_awaited_once_with(None, None, None)
        query, params = self.connection.scalar.await_args.args
        self.assertIn("pg_try_advisory_xact_lock", str(query))
        self.assertEqual(params, {"namespace": JOB_LOCK_NAMESPACE, "key": RADAR_SCAN_LOCK_KEY})

    async def test_overlap_rejects_scan_before_any_work(self) -> None:
        self.connection.scalar.return_value = False
        with patch("app.services.market_radar.runner.run_radar_scan", new_callable=AsyncMock) as scan:
            with self.assertRaises(RadarScanInProgress):
                await run_locked_radar_scan(self.session, force=True)

        scan.assert_not_awaited()
        self.session.commit.assert_not_awaited()
        self.lock_transaction.__aexit__.assert_awaited_once()

    async def test_scan_failure_releases_lock_and_preserves_error(self) -> None:
        error = RuntimeError("scan failed")
        with patch("app.services.market_radar.runner.run_radar_scan", side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                await run_locked_radar_scan(self.session)

        self.assertIs(caught.exception, error)
        self.assertIs(self.lock_transaction.__aexit__.await_args.args[1], error)

    async def test_cancelling_scan_releases_lock(self) -> None:
        started = asyncio.Event()

        async def scan(session, **kwargs):
            started.set()
            await asyncio.Event().wait()

        with patch("app.services.market_radar.runner.run_radar_scan", side_effect=scan):
            task = asyncio.create_task(run_locked_radar_scan(self.session))
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.lock_transaction.__aexit__.assert_awaited_once()
        self.assertIs(self.lock_transaction.__aexit__.await_args.args[0], asyncio.CancelledError)

    async def test_manual_scan_returns_conflict_when_worker_holds_lock(self) -> None:
        self.connection.scalar.return_value = False
        with patch("app.services.market_radar.runner.run_radar_scan", new_callable=AsyncMock) as scan:
            async with AsyncClient(transport=ASGITransport(app=self.api()), base_url="http://test") as client:
                response = await client.post("/market-radar/scan", json={"force": True})

        self.assertEqual(response.status_code, 409)
        self.assertIn("already running", response.json()["detail"])
        scan.assert_not_awaited()
        self.lock_transaction.__aexit__.assert_awaited_once()

    async def test_manual_scan_uses_shared_lock_and_preserves_request(self) -> None:
        run = SimpleNamespace(
            id=uuid4(), started_at=datetime.now(timezone.utc), finished_at=None,
            status="completed", triggered_by_user_id="request-user",
            jurisdictions_requested=["US"], jurisdictions_scanned=["US"],
            jurisdictions_skipped=[], vendor_calls=1, cache_hits=2, catalog_count=3,
            working_set_count=3, flagged_count=0, promoted_count=0,
            promotion_owner_ids=[], notes=[], errors=[],
        )
        with patch("app.services.market_radar.runner.run_radar_scan", return_value=run) as scan:
            async with AsyncClient(transport=ASGITransport(app=self.api()), base_url="http://test") as client:
                response = await client.post(
                    "/market-radar/scan", json={"force": True, "jurisdictions": ["US"]}
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(run.id))
        scan.assert_awaited_once_with(
            self.session, jurisdictions=["US"], force=True,
            triggered_by_user_id="request-user", owner_user_id=None,
        )
        self.lock_transaction.__aexit__.assert_awaited_once_with(None, None, None)

    async def test_worker_skips_manual_scan_overlap_and_disposes_engine(self) -> None:
        self.connection.scalar.return_value = False
        session_context = AsyncMock()
        session_context.__aenter__.return_value = self.session
        with (
            patch("app.workers.tasks.radar_scan.create_async_engine", return_value=self.engine),
            patch("app.workers.tasks.radar_scan.async_sessionmaker", return_value=MagicMock(return_value=session_context)),
            patch("app.services.market_radar.runner.run_radar_scan", new_callable=AsyncMock) as scan,
            self.assertLogs("app.workers.tasks.radar_scan", level="INFO") as logs,
        ):
            await _run()

        self.assertIn("radar_scan_skipped_overlap", logs.output[0])
        scan.assert_not_awaited()
        session_context.__aexit__.assert_awaited_once()
        self.lock_transaction.__aexit__.assert_awaited_once()
        self.engine.dispose.assert_awaited_once()

    async def test_worker_failure_releases_session_lock_and_engine(self) -> None:
        session_context = AsyncMock()
        session_context.__aenter__.return_value = self.session
        with (
            patch("app.workers.tasks.radar_scan.create_async_engine", return_value=self.engine),
            patch("app.workers.tasks.radar_scan.async_sessionmaker", return_value=MagicMock(return_value=session_context)),
            patch("app.services.market_radar.runner.run_radar_scan", side_effect=RuntimeError("scan failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "scan failed"):
                await _run()

        session_context.__aexit__.assert_awaited_once()
        self.lock_transaction.__aexit__.assert_awaited_once()
        self.engine.dispose.assert_awaited_once()
