import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import SystemLogEntry
from app.services.administration.system_log import publish_system_log, record_system_log


class SystemLogPublishTests(IsolatedAsyncioTestCase):
    def entry(self) -> SystemLogEntry:
        return SystemLogEntry(
            owner_user_id="owner", level="info", category="market_data",
            event="radar_scan_completed", message="Scan complete.", context={},
        )

    async def test_deferred_log_is_flushed_without_publishing(self) -> None:
        session = SimpleNamespace(add=MagicMock(), flush=AsyncMock())
        with patch("app.services.administration.system_log.publish_event", new_callable=AsyncMock) as publish:
            entry = await record_system_log(
                session, owner_user_id="owner", category="market_data",
                event="radar_scan_completed", message="Scan complete.",
                context={"run_id": "run"}, publish=False,
            )

        session.add.assert_called_once_with(entry)
        session.flush.assert_awaited_once()
        publish.assert_not_awaited()
        self.assertEqual(entry.context, {"run_id": "run"})

    async def test_default_log_publishes_existing_event_shape(self) -> None:
        session = SimpleNamespace(add=MagicMock(), flush=AsyncMock())
        with patch("app.services.administration.system_log.publish_event", new_callable=AsyncMock) as publish:
            await record_system_log(
                session, owner_user_id="owner", category="market_data",
                event="radar_scan_completed", message="Scan complete.", level="warning",
            )

        publish.assert_awaited_once()
        event = publish.await_args.args[0]
        self.assertEqual(event["type"], "system_log.entry")
        self.assertEqual(event["owner_user_id"], "owner")
        self.assertEqual(event["payload"], {
            "level": "warning", "category": "market_data",
            "event": "radar_scan_completed", "message": "Scan complete.",
        })

    async def test_stalled_publish_is_cancelled_at_deadline(self) -> None:
        cancelled = asyncio.Event()

        async def stalled_publish(event):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with (
            patch("app.services.administration.system_log.publish_event", side_effect=stalled_publish),
            patch("app.services.administration.system_log.SYSTEM_LOG_PUBLISH_TIMEOUT_SECONDS", 0.01),
            self.assertLogs("app.services.administration.system_log", level="WARNING") as logs,
        ):
            await asyncio.wait_for(publish_system_log(self.entry()), timeout=1)

        self.assertTrue(cancelled.is_set())
        self.assertIn("system_log_publish_timed_out", logs.output[0])

    async def test_publish_failure_does_not_fail_completed_work(self) -> None:
        with (
            patch("app.services.administration.system_log.publish_event", side_effect=RuntimeError("Redis unavailable")),
            self.assertLogs("app.services.administration.system_log", level="WARNING") as logs,
        ):
            await publish_system_log(self.entry())

        self.assertIn("system_log_publish_failed", logs.output[0])

    async def test_event_construction_failure_is_best_effort(self) -> None:
        with (
            patch("app.services.administration.system_log.system_log_entry_event", side_effect=ValueError("invalid event")),
            patch("app.services.administration.system_log.publish_event", new_callable=AsyncMock) as publish,
            self.assertLogs("app.services.administration.system_log", level="WARNING"),
        ):
            await publish_system_log(self.entry())

        publish.assert_not_awaited()

    async def test_external_cancellation_is_preserved(self) -> None:
        started = asyncio.Event()

        async def stalled_publish(event):
            started.set()
            await asyncio.Event().wait()

        with patch("app.services.administration.system_log.publish_event", side_effect=stalled_publish):
            task = asyncio.create_task(publish_system_log(self.entry()))
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
