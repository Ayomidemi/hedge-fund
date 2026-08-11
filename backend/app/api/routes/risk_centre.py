from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.risk_centre import (
    PreTradeRiskCheckCreate,
    PreTradeRiskCheckResponse,
    RiskCentreOverviewResponse,
    RiskSnapshotCaptureResponse,
    StressScenarioCreate,
    StressTestResultResponse,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.risk.risk_centre import (
    build_risk_centre_overview,
    capture_risk_snapshot,
    check_pre_trade_risk,
    run_custom_stress_test,
)

router = APIRouter(prefix="/risk-centre")


@router.get("/overview", response_model=RiskCentreOverviewResponse)
async def read_risk_centre_overview(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RiskCentreOverviewResponse:
    return await build_risk_centre_overview(session, user)


@router.post(
    "/snapshots",
    response_model=RiskSnapshotCaptureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_risk_snapshot(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RiskSnapshotCaptureResponse:
    return await capture_risk_snapshot(session, user)


@router.post("/stress-tests", response_model=StressTestResultResponse)
async def create_custom_stress_test(
    payload: StressScenarioCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> StressTestResultResponse:
    return await run_custom_stress_test(session, payload, user)


@router.post("/pre-trade-check", response_model=PreTradeRiskCheckResponse)
async def create_pre_trade_risk_check(
    payload: PreTradeRiskCheckCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> PreTradeRiskCheckResponse:
    return await check_pre_trade_risk(session, payload, user)
