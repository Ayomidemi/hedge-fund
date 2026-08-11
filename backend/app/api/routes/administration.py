from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.administration import AdministrationOverviewResponse
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.administration.overview import build_administration_overview

router = APIRouter(prefix="/administration")


@router.get("/overview", response_model=AdministrationOverviewResponse)
async def read_administration_overview(
    log_limit: int = Query(default=100, ge=1, le=500),
    log_category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AdministrationOverviewResponse:
    return await build_administration_overview(
        session,
        user,
        log_limit=log_limit,
        log_category=log_category,
    )
