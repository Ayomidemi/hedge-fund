from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.idempotency import optional_idempotency_key
from app.api.schemas.paper_fund import PaperFundResponse, PaperStart
from app.core.auth import AuthenticatedUser, require_capital_user
from app.db.session import get_session
from app.services.paper_fund import engine

router = APIRouter(prefix="/paper-fund")


@router.get("", response_model=PaperFundResponse)
async def read_paper_fund(run_id: UUID | None = None,
                          user: AuthenticatedUser = Depends(require_capital_user),
                          session: AsyncSession = Depends(get_session)):
    return await engine.overview(session, user.id, run_id=run_id)


@router.post("/start", response_model=PaperFundResponse)
async def start_paper_fund(payload: PaperStart,
                           user: AuthenticatedUser = Depends(require_capital_user),
                           session: AsyncSession = Depends(get_session),
                           idempotency_key: str | None = Depends(optional_idempotency_key)):
    return await engine.start_run(session, user.id, payload, idempotency_key=idempotency_key)


@router.post("/pause", response_model=PaperFundResponse)
async def pause_paper_fund(user: AuthenticatedUser = Depends(require_capital_user),
                           session: AsyncSession = Depends(get_session)):
    return await engine.control_run(session, user.id, "pause")


@router.post("/resume", response_model=PaperFundResponse)
async def resume_paper_fund(user: AuthenticatedUser = Depends(require_capital_user),
                            session: AsyncSession = Depends(get_session)):
    return await engine.control_run(session, user.id, "resume")


@router.post("/cycle", response_model=PaperFundResponse)
async def cycle_paper_fund(user: AuthenticatedUser = Depends(require_capital_user),
                           session: AsyncSession = Depends(get_session)):
    return await engine.cycle(session, user.id)
