from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.research_lab import ResearchLabOverviewResponse
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.research_lab.lab import build_research_lab_overview

router = APIRouter(prefix="/research-lab")


@router.get("/overview", response_model=ResearchLabOverviewResponse)
async def read_research_lab_overview(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> ResearchLabOverviewResponse:
    return await build_research_lab_overview(session, user)
