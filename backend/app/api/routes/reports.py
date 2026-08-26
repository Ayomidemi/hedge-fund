from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.reporting import (
    MonthlyReportResponse,
    ReportKind,
    ReportSnapshotCreate,
    ReportSnapshotResponse,
    ReportSnapshotUpdate,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.reporting.monthly import (
    build_monthly_report,
    build_report,
    delete_report_snapshot,
    get_report_snapshot,
    list_report_snapshots,
    save_report_snapshot,
    update_report_snapshot,
)

router = APIRouter(prefix="/reports")


@router.get("/current", response_model=MonthlyReportResponse)
async def read_current_report(
    report_kind: ReportKind = Query(default="monthly", alias="kind"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    quarter: int | None = Query(default=None, ge=1, le=4),
    as_of: date | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> MonthlyReportResponse:
    return await build_report(
        session,
        user,
        report_kind=report_kind,
        year=year,
        month=month,
        quarter=quarter,
        as_of=as_of,
    )


@router.get("/monthly", response_model=MonthlyReportResponse)
async def read_monthly_report(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> MonthlyReportResponse:
    return await build_monthly_report(session, user, year=year, month=month)


@router.get("/snapshots", response_model=list[ReportSnapshotResponse])
async def read_report_snapshots(
    limit: int = Query(default=20, ge=1, le=50),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> list[ReportSnapshotResponse]:
    return await list_report_snapshots(session, user, limit=limit)


@router.get("/snapshots/{snapshot_id}", response_model=ReportSnapshotResponse)
async def read_report_snapshot(
    snapshot_id: UUID,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> ReportSnapshotResponse:
    snapshot = await get_report_snapshot(session, user, snapshot_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report snapshot not found.",
        )
    return snapshot


@router.post("/snapshots", response_model=ReportSnapshotResponse)
async def create_report_snapshot(
    payload: ReportSnapshotCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> ReportSnapshotResponse:
    return await save_report_snapshot(
        session,
        user,
        report_kind=payload.report_kind,
        year=payload.year,
        month=payload.month,
        quarter=payload.quarter,
        as_of=payload.as_of,
    )


@router.patch("/snapshots/{snapshot_id}", response_model=ReportSnapshotResponse)
async def patch_report_snapshot(
    snapshot_id: UUID,
    payload: ReportSnapshotUpdate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> ReportSnapshotResponse:
    snapshot = await update_report_snapshot(session, user, snapshot_id, payload.title)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report snapshot not found.",
        )
    return snapshot


@router.delete("/snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_report_snapshot(
    snapshot_id: UUID,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    deleted = await delete_report_snapshot(session, user, snapshot_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report snapshot not found.",
        )
