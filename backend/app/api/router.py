from fastapi import APIRouter

from app.api.routes import health, operating_core, ticker_intelligence

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(operating_core.router, tags=["operating-core"])
api_router.include_router(ticker_intelligence.router, tags=["ticker-intelligence"])
