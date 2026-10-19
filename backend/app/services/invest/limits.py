"""Resting Invest limit orders. Market orders stay immediate."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Instrument, InstrumentQuote, RetailAccount, RetailOrder, RetailPosition, RetailTransaction
from app.services.market_data.ingestion import ingest_quotes
from app.services.market_radar.execution import quote_rejection
from app.services.paper_fund.calendar import market_blocker
from app.services.paper_fund.engine import fee, money, utc

ZERO = Decimal("0")
CENT = Decimal("0.01")
QTY = Decimal("0.00000001")
PRICE = Decimal("0.000001")
FEE_POLICY = {"fee_bps": 5}


def slip_buy(price: Decimal) -> Decimal:
    return (price * Decimal("1.001")).quantize(CENT, rounding=ROUND_CEILING)


def slip_sell(price: Decimal) -> Decimal:
    return (price * Decimal("0.999")).quantize(CENT, rounding=ROUND_FLOOR)


def reserve_for(limit_price: Decimal, quantity: Decimal) -> Decimal:
    return money(limit_price * quantity + fee(limit_price * quantity, FEE_POLICY))


def limit_decision(order, quote, now: datetime) -> str:
    """Return fill, expire, or wait. The caller books the cash."""
    now = utc(now)
    if order.expires_at is not None and now >= utc(order.expires_at):
        return "expire"
    if market_blocker(now) or quote_rejection(quote, now):
        return "wait"
    if order.submitted_at is None or utc(quote.as_of) <= utc(order.submitted_at):
        return "wait"
    if order.side == "BUY":
        return "fill" if slip_buy(quote.price) <= order.limit_price else "wait"
    return "fill" if slip_sell(quote.price) >= order.limit_price else "wait"


async def refresh_resting_quotes(session: AsyncSession, *, now: datetime | None = None) -> int:
    now = utc(now or datetime.now())
    if market_blocker(now):
        return 0
    rows = (await session.execute(
        select(Instrument, InstrumentQuote, RetailOrder)
        .join(RetailOrder, RetailOrder.instrument_id == Instrument.id)
        .outerjoin(InstrumentQuote, InstrumentQuote.instrument_id == Instrument.id)
        .where(RetailOrder.status == "PENDING", RetailOrder.order_type == "limit")
    )).all()
    universe: dict[str, set] = {}
    for instrument, quote, order in rows:
        needs_later = quote is None or quote.as_of is None or utc(quote.as_of) <= utc(order.submitted_at)
        if quote_rejection(quote, now) or needs_later:
            universe.setdefault(instrument.ticker, set()).add(instrument.id)
    if not universe:
        return 0
    result = await ingest_quotes(session, {ticker: list(ids) for ticker, ids in universe.items()})
    await session.commit()
    return result.success_count


async def advance_resting_orders(session: AsyncSession, account: RetailAccount, now: datetime) -> Decimal:
    """Fill, expire, or leave resting limits. Returns cash still reserved by them."""
    orders = list(await session.scalars(
        select(RetailOrder).where(
            RetailOrder.account_id == account.id,
            RetailOrder.status == "PENDING",
            RetailOrder.order_type == "limit",
        ).options(selectinload(RetailOrder.instrument)).with_for_update()
    ))
    if not orders:
        return ZERO
    ids = {order.instrument_id for order in orders}
    quotes = {quote.instrument_id: quote for quote in await session.scalars(
        select(InstrumentQuote).where(InstrumentQuote.instrument_id.in_(ids))
    )}
    for order in orders:
        decision = limit_decision(order, quotes.get(order.instrument_id), now)
        if decision == "wait":
            continue
        if decision == "expire":
            await _release(session, account, order)
            order.status = "EXPIRED"
            order.reject_reason = "Limit expired at the session close."
            continue
        quote = quotes[order.instrument_id]
        if order.side == "BUY":
            await _fill_buy(session, account, order, slip_buy(quote.price), now)
        else:
            await _fill_sell(session, account, order, max(CENT, slip_sell(quote.price)), now)
    return money(sum((reserve_for(order.limit_price, order.quantity) for order in orders if order.status == "PENDING"), ZERO))


async def release_resting_order(session: AsyncSession, account: RetailAccount, order: RetailOrder) -> None:
    if order.order_type == "limit" and order.status == "PENDING":
        await _release(session, account, order)


async def _release(session: AsyncSession, account: RetailAccount, order: RetailOrder) -> None:
    if order.side == "BUY":
        account.reserved_cash = money((account.reserved_cash or ZERO) - reserve_for(order.limit_price, order.quantity))
        return
    position = await _position(session, account.id, order.instrument_id)
    if position is not None:
        position.reserved_quantity = max(ZERO, (position.reserved_quantity or ZERO) - order.quantity)


async def _fill_buy(session, account, order, price: Decimal, now: datetime) -> None:
    await _release(session, account, order)
    cost = money(price * order.quantity + fee(price * order.quantity, FEE_POLICY))
    if cost > account.cash_balance:
        order.status = "CANCELLED"
        order.reject_reason = "Cash changed before the limit could fill."
        return
    account.cash_balance = money(account.cash_balance - cost)
    position = await _position(session, account.id, order.instrument_id)
    if position is None:
        position = RetailPosition(
            account_id=account.id, instrument_id=order.instrument_id, quantity=order.quantity,
            average_cost=(cost / order.quantity).quantize(PRICE, rounding=ROUND_HALF_UP),
            cost_basis=cost, realized_pnl=ZERO,
        )
        session.add(position)
    else:
        new_qty = position.quantity + order.quantity
        new_cost = position.cost_basis + cost
        position.quantity = new_qty
        position.cost_basis = new_cost
        position.average_cost = (new_cost / new_qty).quantize(PRICE, rounding=ROUND_HALF_UP)
    _complete(session, account, order, price, cost, now, "BUY", -cost, "Limit buy filled.")


async def _fill_sell(session, account, order, price: Decimal, now: datetime) -> None:
    position = await _position(session, account.id, order.instrument_id)
    if position is None or position.quantity < order.quantity:
        await _release(session, account, order)
        order.status = "CANCELLED"
        order.reject_reason = "The position was no longer available."
        return
    position.reserved_quantity = max(ZERO, (position.reserved_quantity or ZERO) - order.quantity)
    proceeds = money(price * order.quantity - fee(price * order.quantity, FEE_POLICY))
    realized = money(proceeds - position.average_cost * order.quantity)
    position.quantity = (position.quantity - order.quantity).quantize(QTY)
    position.cost_basis = money(position.average_cost * position.quantity)
    position.realized_pnl = money((position.realized_pnl or ZERO) + realized)
    account.realized_pnl = money((account.realized_pnl or ZERO) + realized)
    account.cash_balance = money(account.cash_balance + proceeds)
    if position.quantity <= 0:
        await session.delete(position)
    _complete(session, account, order, price, proceeds, now, "SELL", proceeds, "Limit sell filled.")


def _complete(session, account, order, price, notional, now, side, cash_amount, description) -> None:
    order.status = "FILLED"
    order.filled_at = now
    order.average_fill_price = price.quantize(PRICE, rounding=ROUND_HALF_UP)
    order.filled_quantity = order.quantity
    order.notional = notional
    session.add(RetailTransaction(
        account_id=account.id, entry_type=side, amount=cash_amount, currency=account.base_currency,
        instrument_id=order.instrument_id, occurred_at=now, source="paper",
        broker_reference=order.broker_order_id, description=description,
    ))


async def _position(session, account_id, instrument_id):
    return await session.scalar(
        select(RetailPosition).where(
            RetailPosition.account_id == account_id,
            RetailPosition.instrument_id == instrument_id,
        ).with_for_update()
    )
