from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.administration import AdministrationOverviewResponse, SystemLogListResponse
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.administration.overview import (
    build_administration_overview,
    build_system_log_page,
)

router = APIRouter(prefix="/administration")


@router.get("/overview", response_model=AdministrationOverviewResponse)
async def read_administration_overview(
    log_limit: int = Query(default=25, ge=1, le=500),
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


@router.get("/logs", response_model=SystemLogListResponse)
async def read_administration_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    log_category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> SystemLogListResponse:
    return await build_system_log_page(
        session,
        user,
        page=page,
        page_size=page_size,
        category=log_category,
    )
