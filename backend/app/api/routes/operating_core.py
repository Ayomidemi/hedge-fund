from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.operating_core import (
    CashAdjustmentCreate,
    CashDepositCreate,
    CashLedgerEntryCreate,
    CashLedgerEntryResponse,
    CashWithdrawalCreate,
    ManualTradeCreate,
    ManualTradeUpdate,
    PortfolioDashboardResponse,
    TradeJournalResponse,
    TradeResponse,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.portfolio.operating_core import (
    TradeNotFoundError,
    TradeRiskApprovalError,
    create_cash_adjustment,
    create_cash_deposit,
    create_cash_withdrawal,
    create_manual_trade,
    get_dashboard,
    get_trade_journal,
    list_cash_ledger_history,
    update_manual_trade,
)

router = APIRouter(prefix="/operating-core")


@router.get("/dashboard", response_model=PortfolioDashboardResponse)
async def read_dashboard(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> PortfolioDashboardResponse:
    return await get_dashboard(session, user)


@router.post(
    "/cash-ledger",
    response_model=CashLedgerEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_cash_entry(
    payload: CashLedgerEntryCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> CashLedgerEntryResponse:
    return await create_cash_deposit(session, payload, user)


@router.post(
    "/cash-ledger/deposits",
    response_model=CashLedgerEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_cash_deposit(
    payload: CashDepositCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> CashLedgerEntryResponse:
    return await create_cash_deposit(session, payload, user)


@router.post(
    "/cash-ledger/withdrawals",
    response_model=CashLedgerEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_cash_withdrawal(
    payload: CashWithdrawalCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> CashLedgerEntryResponse:
    return await create_cash_withdrawal(session, payload, user)


@router.post(
    "/cash-ledger/adjustments",
    response_model=CashLedgerEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_cash_adjustment(
    payload: CashAdjustmentCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> CashLedgerEntryResponse:
    return await create_cash_adjustment(session, payload, user)


@router.get("/cash-ledger/history", response_model=list[CashLedgerEntryResponse])
async def read_cash_ledger_history(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> list[CashLedgerEntryResponse]:
    return await list_cash_ledger_history(session, user)


@router.get("/cash-ledger", response_model=list[CashLedgerEntryResponse])
async def read_cash_ledger_history_compat(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> list[CashLedgerEntryResponse]:
    return await list_cash_ledger_history(session, user)


@router.post(
    "/trades",
    response_model=TradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_manual_trade(
    payload: ManualTradeCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TradeResponse:
    try:
        return await create_manual_trade(session, payload, user)
    except TradeRiskApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.patch("/trades/{trade_id}", response_model=TradeResponse)
async def edit_manual_trade(
    trade_id: UUID,
    payload: ManualTradeUpdate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TradeResponse:
    try:
        return await update_manual_trade(session, trade_id, payload, user)
    except TradeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/trades", response_model=TradeJournalResponse)
async def read_trade_journal(
    limit: int = Query(default=100, ge=1, le=500),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TradeJournalResponse:
    return await get_trade_journal(session, user, limit=limit)
