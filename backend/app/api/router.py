from fastapi import APIRouter, Depends

from app.api.routes import auth, health, operating_core, reports, risk_centre, strategy_pods, ticker_intelligence
from app.core.auth import require_authenticated_user

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(
    auth.router,
    tags=["auth"],
    dependencies=[Depends(require_authenticated_user)],
)
api_router.include_router(
    operating_core.router,
    tags=["operating-core"],
    dependencies=[Depends(require_authenticated_user)],
)
api_router.include_router(
    ticker_intelligence.router,
    tags=["ticker-intelligence"],
    dependencies=[Depends(require_authenticated_user)],
)
api_router.include_router(
    reports.router,
    tags=["reports"],
    dependencies=[Depends(require_authenticated_user)],
)
api_router.include_router(
    risk_centre.router,
    tags=["risk-centre"],
    dependencies=[Depends(require_authenticated_user)],
)
api_router.include_router(
    strategy_pods.router,
    tags=["strategy-pods"],
    dependencies=[Depends(require_authenticated_user)],
)
