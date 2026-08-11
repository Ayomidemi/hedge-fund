from fastapi import APIRouter

from app.api.routes import (
    administration,
    attribution,
    auth,
    health,
    operating_core,
    opportunity_queue,
    reports,
    research_lab,
    risk_centre,
    strategy_pods,
    ticker_intelligence,
    websocket,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(operating_core.router, tags=["operating-core"])
api_router.include_router(administration.router, tags=["administration"])
api_router.include_router(opportunity_queue.router, tags=["opportunity-queue"])
api_router.include_router(attribution.router, tags=["attribution"])
api_router.include_router(ticker_intelligence.router, tags=["ticker-intelligence"])
api_router.include_router(reports.router, tags=["reports"])
api_router.include_router(research_lab.router, tags=["research-lab"])
api_router.include_router(risk_centre.router, tags=["risk-centre"])
api_router.include_router(strategy_pods.router, tags=["strategy-pods"])
api_router.include_router(websocket.router, tags=["realtime"])
