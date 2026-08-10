from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.reporting import MonthlyReportResponse
from app.db.session import get_session
from app.services.reporting.monthly import build_monthly_report

router = APIRouter(prefix="/reports")


@router.get("/monthly", response_model=MonthlyReportResponse)
async def read_monthly_report(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> MonthlyReportResponse:
    return await build_monthly_report(session, year=year, month=month)
