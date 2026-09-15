from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.invest import (
    InvestAccountResponse,
    InvestCashRequest,
    InvestHolding,
    InvestHomeResponse,
    InvestInstrumentResponse,
    InvestOrderCreate,
    InvestOrderResponse,
    InvestTransactionResponse,
    InvestWatchlistItemResponse,
)
from app.api.schemas.operating_core import InstrumentCreate
from app.core.auth import AuthenticatedUser
from app.core.config import settings
from app.models import Instrument, RetailAccount, RetailOrder, RetailWatchlistItem
from app.services.brokerage.gateway import get_broker_provider
from app.services.brokerage.paper import PaperBrokerProvider
from app.services.brokerage.protocol import (
    BrokerValidationError,
    CashRequest,
    SubmitOrderRequest,
)
from app.services.market_data.quote_cache import get_cached_quote_price, get_or_fetch_quote_price
from app.services.portfolio.operating_core import upsert_instrument
from app.services.ticker_intelligence.market_data import search_ticker_suggestions

MONEY = Decimal("0.01")


class InvestError(Exception):
    pass


class InvestValidationError(InvestError):
    pass


class InvestNotFoundError(InvestError):
    pass


async def get_or_create_account(
    session: AsyncSession, user: AuthenticatedUser
) -> RetailAccount:
    account = await session.scalar(
        select(RetailAccount).where(RetailAccount.user_id == user.id)
    )
    if account is not None:
        return account

    starting = settings.invest_paper_starting_cash
    account_id = uuid4()
    account = RetailAccount(
        id=account_id,
        user_id=user.id,
        account_number=_account_number(),
        broker_provider="PAPER",
        broker_account_id=str(account_id),
        status="active",
        base_currency="USD",
        cash_balance=starting,
    )
    session.add(account)
    from app.models import RetailTransaction

    session.add(
        RetailTransaction(
            account_id=account.id,
            entry_type="DEPOSIT",
            amount=starting,
            currency="USD",
            occurred_at=datetime.now(timezone.utc),
            source="paper",
            description="Initial paper buying power.",
        )
    )
    await session.flush()
    return account


async def get_account_response(
    session: AsyncSession, user: AuthenticatedUser
) -> InvestAccountResponse:
    account = await get_or_create_account(session, user)
    broker = get_broker_provider(session, account.broker_provider)
    snapshot = await broker.get_account(account.broker_account_id)
    return _account_response(account, snapshot.balances.cash, snapshot.balances.buying_power)


async def get_home(
    session: AsyncSession, user: AuthenticatedUser
) -> InvestHomeResponse:
    account = await get_or_create_account(session, user)
    broker = get_broker_provider(session, account.broker_provider)
    balances = await broker.get_balances(account.broker_account_id)
    broker_positions = await broker.get_positions(account.broker_account_id)
    holdings = await _holdings(session, broker_positions)
    invested = sum((item.market_value for item in holdings), Decimal("0")).quantize(MONEY)
    portfolio_value = (balances.cash + invested).quantize(MONEY)
    return InvestHomeResponse(
        account=_account_response(account, balances.cash, balances.buying_power),
        portfolio_value=portfolio_value,
        cash=balances.cash,
        invested=invested,
        holdings=holdings,
        headlines=[
            "This is paper trading — no real money is at risk.",
            "Search a name, review it, then buy a small amount to prove the loop.",
        ],
    )


async def list_positions(
    session: AsyncSession, user: AuthenticatedUser
) -> list[InvestHolding]:
    home = await get_home(session, user)
    return home.holdings


async def submit_order(
    session: AsyncSession, user: AuthenticatedUser, payload: InvestOrderCreate
) -> InvestOrderResponse:
    account = await get_or_create_account(session, user)
    if payload.amount is None and payload.quantity is None:
        raise InvestValidationError("Enter an amount or a quantity.")
    await _require_instrument(session, payload.ticker)
    broker = get_broker_provider(session, account.broker_provider)
    try:
        result = await broker.submit_order(
            account.broker_account_id,
            SubmitOrderRequest(
                symbol=payload.ticker,
                side=payload.side,
                order_type=payload.order_type,
                quantity=payload.quantity,
                notional=payload.amount,
            ),
        )
    except BrokerValidationError as exc:
        raise InvestValidationError(str(exc)) from exc

    instrument = await session.scalar(
        select(Instrument).where(Instrument.ticker == result.symbol)
    )
    order = await session.scalar(
        select(RetailOrder).where(RetailOrder.broker_order_id == result.broker_order_id)
    )
    if order is None or instrument is None:
        raise InvestError("Order could not be loaded after fill.")
    await session.commit()
    return _order_response(order, instrument)


async def list_orders(
    session: AsyncSession, user: AuthenticatedUser
) -> list[InvestOrderResponse]:
    account = await get_or_create_account(session, user)
    rows = list(
        await session.scalars(
            select(RetailOrder)
            .options(selectinload(RetailOrder.instrument))
            .where(RetailOrder.account_id == account.id)
            .order_by(RetailOrder.submitted_at.desc())
        )
    )
    return [_order_response(row, row.instrument) for row in rows]


async def get_order(
    session: AsyncSession, user: AuthenticatedUser, order_id: UUID
) -> InvestOrderResponse:
    account = await get_or_create_account(session, user)
    order = await session.scalar(
        select(RetailOrder)
        .options(selectinload(RetailOrder.instrument))
        .where(RetailOrder.id == order_id)
        .where(RetailOrder.account_id == account.id)
    )
    if order is None:
        raise InvestNotFoundError("Order was not found.")
    return _order_response(order, order.instrument)


async def cancel_order(
    session: AsyncSession, user: AuthenticatedUser, order_id: UUID
) -> InvestOrderResponse:
    account = await get_or_create_account(session, user)
    order = await session.scalar(
        select(RetailOrder)
        .options(selectinload(RetailOrder.instrument))
        .where(RetailOrder.id == order_id)
        .where(RetailOrder.account_id == account.id)
    )
    if order is None:
        raise InvestNotFoundError("Order was not found.")
    instrument = order.instrument
    broker = get_broker_provider(session, account.broker_provider)
    try:
        await broker.cancel_order(account.broker_account_id, order.broker_order_id)
    except BrokerValidationError as exc:
        raise InvestValidationError(str(exc)) from exc
    await session.commit()
    return _order_response(order, instrument)


async def list_transactions(
    session: AsyncSession, user: AuthenticatedUser
) -> list[InvestTransactionResponse]:
    from app.models import RetailTransaction

    account = await get_or_create_account(session, user)
    rows = list(
        await session.scalars(
            select(RetailTransaction)
            .options(selectinload(RetailTransaction.instrument))
            .where(RetailTransaction.account_id == account.id)
            .order_by(RetailTransaction.occurred_at.desc())
            .limit(100)
        )
    )
    return [
        InvestTransactionResponse(
            id=row.id,
            entry_type=row.entry_type,
            amount=row.amount,
            currency=row.currency,
            ticker=row.instrument.ticker if row.instrument is not None else None,
            occurred_at=row.occurred_at,
            description=row.description,
        )
        for row in rows
    ]


async def add_paper_cash(
    session: AsyncSession, user: AuthenticatedUser, payload: InvestCashRequest
) -> InvestAccountResponse:
    account = await get_or_create_account(session, user)
    broker = get_broker_provider(session, account.broker_provider)
    try:
        balances = await broker.deposit(
            account.broker_account_id,
            CashRequest(amount=payload.amount, currency=account.base_currency),
        )
    except BrokerValidationError as exc:
        raise InvestValidationError(str(exc)) from exc
    await session.commit()
    return _account_response(account, balances.cash, balances.buying_power)


async def reset_paper_account(
    session: AsyncSession, user: AuthenticatedUser
) -> InvestAccountResponse:
    account = await get_or_create_account(session, user)
    broker = get_broker_provider(session, account.broker_provider)
    if not isinstance(broker, PaperBrokerProvider):
        raise InvestValidationError("Only paper accounts can be reset.")
    snapshot = await broker.reset_account(
        account.broker_account_id, settings.invest_paper_starting_cash
    )
    await session.commit()
    return _account_response(
        account, snapshot.balances.cash, snapshot.balances.buying_power
    )


async def list_watchlist(
    session: AsyncSession, user: AuthenticatedUser
) -> list[InvestWatchlistItemResponse]:
    rows = list(
        await session.scalars(
            select(RetailWatchlistItem)
            .options(selectinload(RetailWatchlistItem.instrument))
            .where(RetailWatchlistItem.user_id == user.id)
            .order_by(RetailWatchlistItem.date_added.desc())
        )
    )
    items: list[InvestWatchlistItemResponse] = []
    for row in rows:
        price = await get_cached_quote_price(session, row.instrument.ticker)
        items.append(
            InvestWatchlistItemResponse(
                id=row.id,
                ticker=row.instrument.ticker,
                name=row.instrument.name,
                notes=row.notes,
                date_added=row.date_added,
                price=price,
            )
        )
    return items


async def add_watchlist_item(
    session: AsyncSession, user: AuthenticatedUser, ticker: str, notes: str | None
) -> InvestWatchlistItemResponse:
    instrument = await _require_instrument(session, ticker)
    existing = await session.scalar(
        select(RetailWatchlistItem)
        .options(selectinload(RetailWatchlistItem.instrument))
        .where(RetailWatchlistItem.user_id == user.id)
        .where(RetailWatchlistItem.instrument_id == instrument.id)
    )
    if existing is not None:
        return InvestWatchlistItemResponse(
            id=existing.id,
            ticker=existing.instrument.ticker,
            name=existing.instrument.name,
            notes=existing.notes,
            date_added=existing.date_added,
            price=await get_cached_quote_price(session, existing.instrument.ticker),
        )
    item = RetailWatchlistItem(
        user_id=user.id,
        instrument_id=instrument.id,
        notes=notes,
        date_added=datetime.now(timezone.utc),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return InvestWatchlistItemResponse(
        id=item.id,
        ticker=instrument.ticker,
        name=instrument.name,
        notes=item.notes,
        date_added=item.date_added,
        price=await get_cached_quote_price(session, instrument.ticker),
    )


async def remove_watchlist_item(
    session: AsyncSession, user: AuthenticatedUser, ticker: str
) -> None:
    instrument = await session.scalar(
        select(Instrument).where(Instrument.ticker == ticker.strip().upper())
    )
    if instrument is None:
        return
    item = await session.scalar(
        select(RetailWatchlistItem)
        .where(RetailWatchlistItem.user_id == user.id)
        .where(RetailWatchlistItem.instrument_id == instrument.id)
    )
    if item is not None:
        await session.delete(item)
        await session.commit()


async def search_instruments(
    session: AsyncSession, query: str, market: str = "US"
) -> list[InvestInstrumentResponse]:
    suggestions = await search_ticker_suggestions(session, query, market_hint=market)
    results: list[InvestInstrumentResponse] = []
    for item in suggestions:
        price = await get_cached_quote_price(session, item.ticker)
        results.append(
            InvestInstrumentResponse(
                ticker=item.ticker,
                name=item.name,
                asset_class=item.asset_class,
                exchange=item.exchange,
                currency=item.currency,
                sector=item.sector,
                industry=item.industry,
                price=price,
            )
        )
    return results


async def get_instrument(
    session: AsyncSession, ticker: str
) -> InvestInstrumentResponse:
    instrument = await _require_instrument(session, ticker)
    price = await get_or_fetch_quote_price(
        session, instrument.ticker, instrument_id=instrument.id
    )
    return InvestInstrumentResponse(
        ticker=instrument.ticker,
        name=instrument.name,
        asset_class=instrument.asset_class,
        exchange=instrument.exchange,
        currency=instrument.currency,
        sector=instrument.sector,
        industry=instrument.industry,
        price=price,
    )


async def _require_instrument(session: AsyncSession, ticker: str) -> Instrument:
    normalized = ticker.strip().upper()
    instrument = await session.scalar(
        select(Instrument).where(Instrument.ticker == normalized)
    )
    if instrument is not None:
        return instrument
    return await upsert_instrument(
        session,
        InstrumentCreate(ticker=normalized, name=normalized, asset_class="equity"),
    )


async def _holdings(session: AsyncSession, positions) -> list[InvestHolding]:
    holdings: list[InvestHolding] = []
    for item in positions:
        instrument = await session.scalar(
            select(Instrument).where(Instrument.ticker == item.symbol)
        )
        holdings.append(
            InvestHolding(
                ticker=item.symbol,
                name=instrument.name if instrument is not None else item.symbol,
                quantity=item.quantity,
                average_cost=item.average_cost,
                current_price=None if instrument is None else await get_cached_quote_price(
                    session, item.symbol
                ),
                market_value=item.market_value,
                unrealized_pnl=item.unrealized_pnl,
                unrealized_pnl_pct=item.unrealized_pnl_pct,
            )
        )
    return holdings


def _account_response(
    account: RetailAccount, cash: Decimal, buying_power: Decimal
) -> InvestAccountResponse:
    return InvestAccountResponse(
        id=account.id,
        account_number=account.account_number,
        broker_provider=account.broker_provider,
        status=account.status,
        base_currency=account.base_currency,
        cash=cash,
        buying_power=buying_power,
        created_at=account.created_at,
    )


def _order_response(order: RetailOrder, instrument: Instrument) -> InvestOrderResponse:
    return InvestOrderResponse(
        id=order.id,
        ticker=instrument.ticker,
        name=instrument.name,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        notional=order.notional,
        status=order.status,
        submitted_at=order.submitted_at,
        filled_at=order.filled_at,
        average_fill_price=order.average_fill_price,
        warnings=list(order.warnings or []),
    )


def _account_number() -> str:
    return f"PI-{uuid4().hex[:8].upper()}"
