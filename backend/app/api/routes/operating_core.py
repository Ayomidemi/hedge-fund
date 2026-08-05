from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.operating_core import (
    CashLedgerEntryCreate,
    CashLedgerEntryResponse,
    ManualTradeCreate,
    PortfolioDashboardResponse,
    TradeResponse,
)
from app.db.session import get_session
from app.services.portfolio.operating_core import (
    create_cash_entry,
    create_manual_trade,
    get_dashboard,
    list_cash_ledger_history,
)

router = APIRouter(prefix="/operating-core")


@router.get("/dashboard", response_model=PortfolioDashboardResponse)
async def read_dashboard(
    session: AsyncSession = Depends(get_session),
) -> PortfolioDashboardResponse:
    return await get_dashboard(session)


@router.post(
    "/cash-ledger",
    response_model=CashLedgerEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_cash_entry(
    payload: CashLedgerEntryCreate,
    session: AsyncSession = Depends(get_session),
) -> CashLedgerEntryResponse:
    return await create_cash_entry(session, payload)


@router.get("/cash-ledger/history", response_model=list[CashLedgerEntryResponse])
async def read_cash_ledger_history(
    session: AsyncSession = Depends(get_session),
) -> list[CashLedgerEntryResponse]:
    return await list_cash_ledger_history(session)


@router.get("/cash-ledger", response_model=list[CashLedgerEntryResponse])
async def read_cash_ledger_history_compat(
    session: AsyncSession = Depends(get_session),
) -> list[CashLedgerEntryResponse]:
    return await list_cash_ledger_history(session)


@router.post(
    "/trades",
    response_model=TradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_manual_trade(
    payload: ManualTradeCreate,
    session: AsyncSession = Depends(get_session),
) -> TradeResponse:
    return await create_manual_trade(session, payload)
