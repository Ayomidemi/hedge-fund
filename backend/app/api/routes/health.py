from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import PaperEquitySnapshot, PaperFundRun, PaperOrder, Trade

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def database_health_check(
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    await session.execute(text("select 1"))
    try:
        # A current Alembic revision does not prove a previously edited
        # migration installed all mapped columns. Resolve them without reading
        # account rows so a broken trading schema cannot report healthy.
        for model in (PaperFundRun, PaperOrder, PaperEquitySnapshot):
            await session.execute(select(model).limit(0))
        await session.execute(select(Trade.executed_price_base, Trade.fees_base).limit(0))
    except ProgrammingError as exc:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Database schema is out of date. Apply backend migrations.") from exc
    return {"status": "ok"}
