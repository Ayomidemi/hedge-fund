from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.strategy_pods import (
    StrategyPodOverviewResponse,
    StrategyPodResponse,
    StrategyPodSnapshotResponse,
    StrategyPodUpdate,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.strategy_pods.pods import (
    capture_strategy_pod_snapshot,
    get_strategy_pod,
    list_strategy_pod_snapshots,
    list_strategy_pods,
    update_strategy_pod,
)

router = APIRouter(prefix="/strategy-pods")


@router.get("", response_model=StrategyPodOverviewResponse)
async def read_strategy_pods(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyPodOverviewResponse:
    return await list_strategy_pods(session, user)


@router.get("/{code}", response_model=StrategyPodResponse)
async def read_strategy_pod(
    code: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyPodResponse:
    pod = await get_strategy_pod(session, code, user)
    if pod is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy pod not found.",
        )
    return pod


@router.patch("/{code}", response_model=StrategyPodResponse)
async def patch_strategy_pod(
    code: str,
    payload: StrategyPodUpdate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyPodResponse:
    pod = await update_strategy_pod(session, code, payload, user)
    if pod is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy pod not found.",
        )
    return pod


@router.get(
    "/{code}/snapshots",
    response_model=list[StrategyPodSnapshotResponse],
)
async def read_strategy_pod_snapshots(
    code: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> list[StrategyPodSnapshotResponse]:
    snapshots = await list_strategy_pod_snapshots(session, code, user)
    if snapshots is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy pod not found.",
        )
    return snapshots


@router.post(
    "/{code}/snapshots",
    response_model=StrategyPodSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_strategy_pod_snapshot(
    code: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyPodSnapshotResponse:
    snapshot = await capture_strategy_pod_snapshot(session, code, user)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy pod not found.",
        )
    return snapshot
