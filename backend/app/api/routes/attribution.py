from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.attribution import AttributionReportResponse
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.attribution.performance import build_attribution_report

router = APIRouter(prefix="/attribution")


@router.get("/overview", response_model=AttributionReportResponse)
async def read_attribution_overview(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> AttributionReportResponse:
    return await build_attribution_report(session, user)
