"""Serialize radar scans across scheduled jobs and manual requests."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.locks import RADAR_SCAN_LOCK_KEY, hold_job_lock
from app.models import RadarRun
from app.services.market_radar.scan import run_radar_scan


class RadarScanInProgress(RuntimeError):
    def __init__(self) -> None:
        super().__init__("A market radar scan is already running. Try again after it finishes.")


async def run_locked_radar_scan(
    session: AsyncSession,
    *,
    jurisdictions: list[str] | None = None,
    force: bool = False,
    triggered_by_user_id: str | None = None,
    owner_user_id: str | None = None,
) -> RadarRun:
    if session.bind is None:
        raise RuntimeError("Market radar scans require a bound database session.")

    # The dedicated lock transaction survives commits inside the scan and is
    # released by its context manager on success, failure, or cancellation.
    async with hold_job_lock(session.bind, RADAR_SCAN_LOCK_KEY) as locked:
        if not locked:
            raise RadarScanInProgress()
        return await run_radar_scan(
            session,
            jurisdictions=jurisdictions,
            force=force,
            triggered_by_user_id=triggered_by_user_id,
            owner_user_id=owner_user_id,
        )
