from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.opportunity_queue import (
    OpportunityCreate,
    OpportunityQueueResponse,
    OpportunityResponse,
    OpportunityUpdate,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.opportunity_queue.queue import (
    OpportunityNotFoundError,
    OpportunityValidationError,
    create_opportunity,
    list_opportunity_queue,
    update_opportunity,
)

router = APIRouter(prefix="/opportunity-queue")


@router.get("", response_model=OpportunityQueueResponse)
async def read_opportunity_queue(
    candidate_limit: int = Query(default=12, ge=0, le=50),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> OpportunityQueueResponse:
    return await list_opportunity_queue(
        session,
        user,
        candidate_limit=candidate_limit,
    )


@router.post(
    "",
    response_model=OpportunityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_opportunity(
    payload: OpportunityCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> OpportunityResponse:
    try:
        return await create_opportunity(session, user, payload)
    except OpportunityValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
async def patch_opportunity(
    opportunity_id: UUID,
    payload: OpportunityUpdate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> OpportunityResponse:
    try:
        return await update_opportunity(session, user, opportunity_id, payload)
    except OpportunityValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except OpportunityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
