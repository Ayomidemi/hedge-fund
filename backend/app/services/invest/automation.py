"""Invest automatic paper trading on the Invest ledger.

Capital's account, cash and orders are never read or written here. Entry
signals reuse the radar execution gate. Fills wait for a later quote.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Instrument,
    InstrumentQuote,
    InvestManagedOrder,
    RadarRun,
    RadarSnapshot,
    RetailAccount,
    RetailOrder,
    RetailPosition,
    RetailTransaction,
)
from app.services.market_data.ingestion import ingest_quotes
from app.services.market_radar.execution import (
    MAX_SIGNAL_AGE_SECONDS,
    execution_rejection,
    quote_rejection,
)
from app.services.paper_fund.calendar import NEW_YORK, market_blocker
from app.services.paper_fund.eligibility import instrument_rejection
from app.services.paper_fund.engine import fee, money, utc
from app.services.paper_fund.reentry import reentry_rejection
from app.services.risk.policy import position_cap

ZERO = Decimal("0")
CENT = Decimal("0.01")
QTY = Decimal("0.00000001")
PRICE = Decimal("0.000001")
POLICY = {
    "version": 1,
    "profile": "medium",
    "stop_loss_pct": 3,
    "take_profit_pct": 6,
    "slippage_bps": 10,
    "fee_bps": 5,
    "order_ttl_minutes": 30,
    "max_position_pct": 10,
    "max_etf_position_pct": 10,
    "risk_per_trade_pct": Decimal("0.5"),
    "max_positions": 5,
    "cash_reserve_pct": 20,
    "max_drawdown_pct": 5,
    "max_sector_pct": 20,
    "max_aggregate_risk_pct": Decimal("1.5"),
    "max_daily_loss_pct": 2,
    "reentry_cooldown_minutes": 60,
    "max_symbol_entries_per_day": 2,
    "max_symbol_attempts_per_day": 4,
    "max_symbol_daily_turnover_pct": 20,
}


@dataclass
class Book:
    cash: Decimal
    reserved_cash: Decimal
    realized_pnl: Decimal
    high_water_equity: Decimal | None
    max_drawdown_pct: Decimal
    trading_mode: str
    automation_status: str
    halt_reason: str | None
    marks_reliable: bool = True


@dataclass
class Holding:
    instrument_id: object
    sector: str | None
    market_value: Decimal
    asset_class: str


@dataclass
class PlanView:
    """In-memory plan used by tests. ORM rows expose the same fields."""

    id: object
    instrument_id: object
    ticker: str
    sector: str | None
    asset_class: str
    status: str
    quantity: Decimal
    limit_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    reserved_cash: Decimal = ZERO
    entry_price: Decimal | None = None
    exit_price: Decimal | None = None
    entry_fee: Decimal = ZERO
    exit_fee: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    submitted_at: datetime | None = None
    expires_at: datetime | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    entry_quote_at: datetime | None = None
    exit_quote_at: datetime | None = None
    mark_price: Decimal | None = None
    mark_as_of: datetime | None = None
    exit_reason: str | None = None
    signal_id: object | None = None
    evidence: dict = field(default_factory=dict)
    available_quantity: Decimal | None = None
    name: str = ""


def advance(book: Book, plans: list, quotes: dict, holdings: list, now: datetime, *, entry_check=None) -> list[str]:
    """Move plans forward. Cash changes stay on `book` until the caller persists them."""
    now = utc(now)
    blockers: list[str] = []
    session_error = market_blocker(now)
    if session_error:
        blockers.append(session_error)
    accepting = book.trading_mode == "automatic" and book.automation_status != "halted"
    for plan in plans:
        if plan.status != "open" or plan.available_quantity is None:
            continue
        held_qty = Decimal(plan.available_quantity)
        if held_qty <= 0:
            plan.status = "closed"
            plan.closed_at = now
            plan.exit_price = None
            plan.exit_reason = "Position was closed outside the automatic plan."
        elif held_qty < Decimal(plan.quantity):
            plan.evidence = {**(plan.evidence or {}), "planned_quantity": str(plan.quantity)}
            plan.quantity = held_qty
    if not accepting:
        for plan in plans:
            if plan.status == "pending":
                _cancel(book, plan, "cancelled", "Manual mode; automatic entry cancelled." if book.trading_mode != "automatic" else (book.halt_reason or "Automatic entries are halted."))
    for plan in plans:
        if plan.status == "pending" and plan.expires_at is not None and now >= utc(plan.expires_at):
            _cancel(book, plan, "expired", "Entry limit expired without a fill.")
    for plan in plans:
        if plan.status != "open":
            continue
        quote = quotes.get(plan.instrument_id)
        error = quote_rejection(quote, now)
        if error:
            blockers.append(f"{plan.ticker}: {error} Exit waits for a fresh quote.")
        elif not session_error and (plan.mark_as_of is None or utc(quote.as_of) >= utc(plan.mark_as_of)):
            plan.mark_price = quote.price
            plan.mark_as_of = quote.as_of
    _latch_drawdown(book, plans, holdings, blockers)
    for plan in list(plans):
        if plan.status != "open" or session_error:
            continue
        forced = book.automation_status == "halted"
        quote = quotes.get(plan.instrument_id)
        if quote_rejection(quote, now):
            continue
        if plan.entry_quote_at is not None and utc(quote.as_of) <= utc(plan.entry_quote_at):
            continue
        reason = None
        if forced:
            reason = "drawdown_halt"
        elif quote.price <= plan.stop_price:
            reason = "stop_loss"
        elif quote.price >= plan.target_price:
            reason = "take_profit"
        if reason is None:
            continue
        price = max(CENT, _slip_sell(quote.price))
        if reason == "take_profit" and price < plan.target_price:
            continue
        if reason == "take_profit" and _scale_plan(book, plan, price, quote.as_of, now):
            continue
        _sell(book, plan, price, quote.as_of, now, reason)
    if _daily_loss(plans, _equity(book, plans, holdings), now):
        blockers.append("Daily loss limit reached; new entries are paused.")
        for plan in plans:
            if plan.status == "pending":
                _cancel(book, plan, "cancelled", "Daily loss limit reached; entry cancelled.")
    uncertain = not book.marks_reliable or any(
        quote_rejection(quotes.get(plan.instrument_id), now) for plan in plans if plan.status == "open"
    )
    for plan in list(plans):
        if plan.status != "pending" or not accepting or book.automation_status == "halted" or session_error or uncertain:
            continue
        if _daily_loss(plans, _equity(book, plans, holdings), now):
            _cancel(book, plan, "cancelled", "Daily loss limit reached; entry cancelled.")
            continue
        _latch_drawdown(book, plans, holdings, blockers)
        if book.automation_status == "halted":
            _cancel(book, plan, "cancelled", book.halt_reason or "Automatic entries are halted.")
            continue
        quote = quotes.get(plan.instrument_id)
        error = quote_rejection(quote, now)
        if error:
            blockers.append(f"{plan.ticker}: {error}")
            continue
        if plan.submitted_at is not None and utc(quote.as_of) <= utc(plan.submitted_at):
            continue
        if quote.price <= plan.stop_price:
            _cancel(book, plan, "cancelled", "Signal invalidated below the planned stop before entry.")
            continue
        price = _slip_buy(quote.price)
        if price > plan.limit_price:
            continue
        if entry_check is not None:
            decision = entry_check(plan)
            plan.evidence = {**(plan.evidence or {}), "fill_risk": decision}
            if not decision.get("approved", False):
                reason = ("; ".join(decision.get("reasons") or ["Entry check failed."]))[:255]
                _cancel(book, plan, "cancelled", reason)
                blockers.append(f"{plan.ticker}: {reason}")
                continue
        if not _fill_allowed(book, plans, holdings, plan, price):
            _cancel(book, plan, "cancelled", "Cash, reserve or concentration changed before the fill.")
            continue
        _buy(book, plan, price, quote.as_of, now)
    _latch_drawdown(book, plans, holdings, blockers)
    return list(dict.fromkeys(blockers))[:30]


def size_entry(book: Book, plans: list, holdings: list, price: Decimal, sector: str | None, asset_class: str):
    equity = _equity(book, plans, holdings)
    limit = (price * (1 + Decimal(POLICY["slippage_bps"]) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
    stop = (limit * (1 - Decimal(POLICY["stop_loss_pct"]) / 100)).quantize(CENT, rounding=ROUND_FLOOR)
    target = (limit * (1 + Decimal(POLICY["take_profit_pct"]) / 100)).quantize(CENT, rounding=ROUND_CEILING)
    if len(_active_ids(plans, holdings)) >= POLICY["max_positions"] or equity <= 0 or not ZERO < stop < limit < target:
        return 0, limit, stop, target
    cash_budget = book.cash - book.reserved_cash - equity * Decimal(POLICY["cash_reserve_pct"]) / 100
    sector_budget = equity * Decimal(POLICY["max_sector_pct"]) / 100 - _sector_used(plans, holdings, sector, None)
    budget = min(cash_budget, equity * Decimal(str(position_cap(POLICY, asset_class))) / 100, sector_budget)
    risk_budget = equity * Decimal(str(POLICY["risk_per_trade_pct"])) / 100
    risk_budget = min(risk_budget, max(ZERO, equity * Decimal(str(POLICY["max_aggregate_risk_pct"])) / 100 - _aggregate_risk(plans)))
    stop_fill = (stop * (1 - Decimal(POLICY["slippage_bps"]) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
    risk_per_share = limit - stop_fill + (limit + stop_fill) * Decimal(POLICY["fee_bps"]) / 10000
    if budget <= 0 or risk_budget <= 0 or risk_per_share <= 0:
        return 0, limit, stop, target
    return max(0, int(min(budget / limit, risk_budget / risk_per_share))), limit, stop, target


async def refresh_managed_quotes(session: AsyncSession, *, now: datetime | None = None) -> int:
    now = utc(now or datetime.now(timezone.utc))
    if market_blocker(now):
        return 0
    rows = (await session.execute(
        select(Instrument, InstrumentQuote, InvestManagedOrder)
        .join(InvestManagedOrder, InvestManagedOrder.instrument_id == Instrument.id)
        .outerjoin(InstrumentQuote, InstrumentQuote.instrument_id == Instrument.id)
        .where(InvestManagedOrder.status.in_(["pending", "open"]))
    )).all()
    universe: dict[str, set] = {}
    for instrument, quote, plan in rows:
        needs_later = plan.status == "pending" and (quote is None or utc(quote.as_of) <= utc(plan.submitted_at))
        if quote_rejection(quote, now) or needs_later or (quote is not None and (now - utc(quote.as_of)).total_seconds() >= 60):
            universe.setdefault(instrument.ticker, set()).add(instrument.id)
    if not universe:
        return 0
    result = await ingest_quotes(session, {ticker: list(ids) for ticker, ids in universe.items()})
    await session.commit()
    return result.success_count


async def set_trading_mode(session: AsyncSession, user, mode: str):
    from app.db.locks import lock_retail_account
    from app.services.invest.accounts import InvestValidationError, get_or_create_account

    if mode not in {"manual", "automatic"}:
        raise InvestValidationError("Choose Manual or Automatic trading.")
    account = await lock_retail_account(session, await get_or_create_account(session, user))
    if account.broker_provider != "PAPER" or account.status != "active":
        raise InvestValidationError("Automatic paper trading requires an active paper account.")
    plans = list(await session.scalars(
        select(InvestManagedOrder).where(InvestManagedOrder.account_id == account.id).with_for_update()
    ))
    open_plans = [plan for plan in plans if plan.status == "open"]
    if mode == "automatic":
        if account.automation_status == "halted":
            raise InvestValidationError(
                account.halt_reason or "A risk halt is still open. Switch to Manual after positions close, then enable Automatic again."
            )
        account.trading_mode = "automatic"
        account.automation_status = "running"
    else:
        book = _book_from(account)
        for plan in plans:
            if plan.status == "pending":
                _cancel(book, plan, "cancelled", "Manual mode; automatic entry cancelled.")
        account.trading_mode = "manual"
        account.reserved_cash = _reserved(plans)
        if account.automation_status == "halted" and not open_plans:
            account.halt_reason = None
            account.automation_status = "paused"
            account.high_water_equity = None
        elif account.automation_status != "halted":
            account.automation_status = "paused"
    await session.commit()
    return account


async def disarm_for_reset(session: AsyncSession, account: RetailAccount) -> None:
    now = datetime.now(timezone.utc)
    plans = list(await session.scalars(
        select(InvestManagedOrder).where(
            InvestManagedOrder.account_id == account.id,
            InvestManagedOrder.status.in_(["pending", "open"]),
        ).with_for_update()
    ))
    for plan in plans:
        plan.status = "cancelled"
        plan.exit_reason = "Paper account reset."
        plan.reserved_cash = ZERO
        plan.closed_at = now
    account.reserved_cash = ZERO
    account.realized_pnl = ZERO
    account.trading_mode = "manual"
    account.automation_status = "idle"
    account.halt_reason = None
    account.high_water_equity = None
    account.max_drawdown_pct = ZERO
    account.automation_blockers = []


async def cycle_account(session: AsyncSession, account_id, *, now: datetime | None = None) -> None:
    await session.execute(text(
        "SELECT set_config('lock_timeout', '5s', true), "
        "set_config('idle_in_transaction_session_timeout', '30s', true)"
    ))
    now = utc(now or datetime.now(timezone.utc))
    account = await session.scalar(
        select(RetailAccount).where(RetailAccount.id == account_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if account is None or account.broker_provider != "PAPER" or account.status != "active":
        return
    from app.services.invest.limits import advance_resting_orders
    limit_reserved = await advance_resting_orders(session, account, now)
    plans = list(await session.scalars(
        select(InvestManagedOrder).where(InvestManagedOrder.account_id == account.id)
        .execution_options(populate_existing=True)
    ))
    active_ids = [plan.id for plan in plans if plan.status in {"pending", "open"}]
    if active_ids:
        await session.scalars(
            select(InvestManagedOrder).where(InvestManagedOrder.id.in_(active_ids))
            .with_for_update().execution_options(populate_existing=True)
        )
    positions = list(await session.scalars(
        select(RetailPosition).where(RetailPosition.account_id == account.id)
        .with_for_update().execution_options(populate_existing=True)
    ))
    ids = {plan.instrument_id for plan in plans} | {position.instrument_id for position in positions}
    quotes = {quote.instrument_id: quote for quote in await session.scalars(
        select(InstrumentQuote).where(InstrumentQuote.instrument_id.in_(ids)).execution_options(populate_existing=True)
    )} if ids else {}
    instruments = {instrument.id: instrument for instrument in await session.scalars(
        select(Instrument).where(Instrument.id.in_(ids))
    )} if ids else {}
    signal_ids = {plan.signal_id for plan in plans if plan.status == "pending" and plan.signal_id}
    signals = {signal.id: signal for signal in await session.scalars(
        select(RadarSnapshot).where(RadarSnapshot.id.in_(signal_ids))
    )} if signal_ids else {}
    held = {}
    for position in positions:
        held[position.instrument_id] = held.get(position.instrument_id, ZERO) + position.quantity
    for plan in plans:
        if plan.status == "open":
            plan.available_quantity = held.get(plan.instrument_id, ZERO)
    before = {plan.id: plan.status for plan in plans}
    book = _book_from(account)
    holdings, book.marks_reliable = _holdings(positions, plans, instruments, quotes, now)
    def entry_check(plan):
        signal = signals.get(plan.signal_id)
        instrument = instruments.get(plan.instrument_id)
        error = "The original radar signal is unavailable; entry must be rescreened." if signal is None else (
            instrument_rejection(instrument, now) or execution_rejection(signal, quotes.get(plan.instrument_id), now)
        )
        return {"approved": error is None, "reasons": [] if error is None else [error]}
    blockers = advance(book, plans, quotes, holdings, now, entry_check=entry_check)
    realized = account.realized_pnl or ZERO
    for plan in plans:
        pending_scale = (plan.evidence or {}).pop("pending_scale", None)
        if pending_scale and plan.status == "open":
            realized += await _book_partial_sell(session, account, plan, pending_scale, now)
            plan.evidence = {**(plan.evidence or {})}
        if before.get(plan.id) == plan.status:
            continue
        if before.get(plan.id) == "pending" and plan.status == "open":
            await _book_buy(session, account, plan, now)
        elif before.get(plan.id) == "open" and plan.status == "closed" and plan.exit_price is not None:
            realized += await _book_sell(session, account, plan, now)
    accepting = account.trading_mode == "automatic" and book.automation_status != "halted"
    if accepting and book.marks_reliable and not market_blocker(now) and not _daily_loss(plans, _equity(book, plans, holdings), now):
        await _queue(session, account, book, plans, positions, holdings, now, blockers)
    account.cash_balance = money(book.cash)
    account.reserved_cash = money(_reserved(plans) + limit_reserved)
    account.realized_pnl = money(realized)
    account.high_water_equity = book.high_water_equity
    account.max_drawdown_pct = book.max_drawdown_pct
    account.automation_status = book.automation_status
    account.halt_reason = book.halt_reason
    account.last_cycle_at = now
    account.automation_blockers = blockers
    await session.commit()


def _book_from(account: RetailAccount) -> Book:
    return Book(
        cash=account.cash_balance,
        reserved_cash=account.reserved_cash or ZERO,
        realized_pnl=account.realized_pnl or ZERO,
        high_water_equity=account.high_water_equity,
        max_drawdown_pct=account.max_drawdown_pct or ZERO,
        trading_mode=account.trading_mode or "manual",
        automation_status=account.automation_status or "idle",
        halt_reason=account.halt_reason,
        marks_reliable=True,
    )


def _holdings(positions, plans, instruments, quotes, now):
    covered = {}
    for plan in plans:
        if plan.status == "open":
            covered[plan.instrument_id] = covered.get(plan.instrument_id, ZERO) + Decimal(plan.quantity)
    holdings = []
    reliable = True
    for position in positions:
        instrument = instruments.get(position.instrument_id)
        if instrument is None:
            reliable = False
            continue
        extra = position.quantity - covered.get(position.instrument_id, ZERO)
        price = _mark(instrument, quotes.get(position.instrument_id), now)
        if extra > 0:
            if price is None:
                reliable = False
            else:
                holdings.append(Holding(position.instrument_id, instrument.sector, money(extra * price), instrument.asset_class))
        elif (instrument.asset_class or "").lower() in {"equity", "etf"} and price is None:
            reliable = False
    for plan in plans:
        if plan.status == "open" and quote_rejection(quotes.get(plan.instrument_id), now):
            reliable = False
    return holdings, reliable


def _mark(instrument, quote, now):
    if quote is None or quote.price is None or quote.price <= 0 or quote.is_stale:
        return None
    if (instrument.asset_class or "").lower() in {"equity", "etf"} and (instrument.currency or "").upper() == "USD":
        if quote_rejection(quote, now):
            return None
        return quote.price
    return quote.price


async def _queue(session, account, book, plans, positions, holdings, now, blockers):
    radar_run = await session.scalar(
        select(RadarRun).where(RadarRun.status == "completed", RadarRun.started_at <= now)
        .order_by(RadarRun.started_at.desc(), RadarRun.created_at.desc(), RadarRun.id.desc()).limit(1)
    )
    if radar_run is None:
        blockers.append("Waiting for a completed market radar scan.")
        return
    rows = (await session.execute(
        select(RadarSnapshot, Instrument, InstrumentQuote)
        .outerjoin(Instrument, Instrument.ticker == RadarSnapshot.ticker)
        .outerjoin(InstrumentQuote, InstrumentQuote.instrument_id == Instrument.id)
        .where(RadarSnapshot.run_id == radar_run.id, RadarSnapshot.radar_priority.in_(["P0", "P1"]))
        .order_by(RadarSnapshot.priority_score.desc(), RadarSnapshot.ticker)
    )).all()
    held = {position.instrument_id for position in positions}
    managed = {plan.instrument_id for plan in plans if plan.status in {"pending", "open"}}
    run = SimpleNamespace(policy=POLICY)
    added = 0
    for snapshot, instrument, quote in rows:
        def reject(reason):
            if len(blockers) < 30:
                blockers.append(f"{snapshot.ticker}: {reason}")
        if instrument is None:
            reject("No verified instrument is available for this signal.")
            continue
        if instrument.currency != "USD" or instrument.asset_class not in {"equity", "etf"}:
            reject("Automatic Invest entries are limited to USD equities and ETFs.")
            continue
        if instrument.id in held and instrument.id not in managed:
            reject("This instrument is already held manually.")
            continue
        error = reentry_rejection(run, plans, instrument.id, snapshot, now, _equity(book, plans, holdings))
        if error:
            reject(error)
            continue
        error = instrument_rejection(instrument, now) or execution_rejection(snapshot, quote, now)
        if error:
            reject(error)
            continue
        if snapshot.as_of is None or snapshot.source_as_of is None:
            reject("The radar signal is missing an observation timestamp.")
            continue
        expires = min(
            now + timedelta(minutes=POLICY["order_ttl_minutes"]),
            utc(snapshot.as_of) + timedelta(seconds=MAX_SIGNAL_AGE_SECONDS),
            utc(snapshot.source_as_of) + timedelta(seconds=MAX_SIGNAL_AGE_SECONDS),
        )
        if expires <= now:
            reject("The radar signal is already at its entry deadline.")
            continue
        quantity, limit, stop, target = size_entry(book, plans, holdings, quote.price, instrument.sector, instrument.asset_class)
        if quantity <= 0:
            reject("No capacity under cash, reserve, sector or risk limits.")
            continue
        day = now.astimezone(NEW_YORK).date()
        turnover = sum(
            (plan.quantity * plan.entry_price for plan in plans
             if plan.instrument_id == instrument.id and plan.opened_at and utc(plan.opened_at).astimezone(NEW_YORK).date() == day),
            ZERO,
        )
        if turnover + quantity * limit > _equity(book, plans, holdings) * Decimal(POLICY["max_symbol_daily_turnover_pct"]) / 100:
            reject("Daily entry turnover limit reached for this instrument.")
            continue
        reserved = money(limit * quantity + fee(limit * quantity, POLICY))
        if reserved > book.cash - book.reserved_cash:
            reject("Not enough unreserved cash for this entry.")
            continue
        plan = InvestManagedOrder(
            account_id=account.id, instrument_id=instrument.id, signal_id=snapshot.id,
            ticker=instrument.ticker, name=instrument.name, sector=instrument.sector,
            asset_class=instrument.asset_class, status="pending", quantity=quantity,
            limit_price=limit, stop_price=stop, target_price=target, reserved_cash=reserved,
            entry_fee=ZERO, exit_fee=ZERO, realized_pnl=ZERO,
            submitted_at=now, expires_at=expires,
            thesis=f"Confirmed positive radar momentum ({snapshot.change_pct}% session move).",
            evidence={
                "radar_snapshot_id": str(snapshot.id), "radar_run_id": str(radar_run.id),
                "quote_as_of": quote.as_of.isoformat() if quote.as_of else None,
                "quote_source": quote.source, "policy_version": POLICY["version"],
            },
        )
        book.reserved_cash = money(book.reserved_cash + reserved)
        session.add(plan)
        plans.append(plan)
        added += 1
    if not added and not any(plan.status == "pending" for plan in plans):
        blockers.append("No new radar signal currently passes every Invest execution check.")


async def _book_buy(session, account, plan, now):
    price = Decimal(plan.entry_price)
    quantity = Decimal(plan.quantity)
    cash_notional = money(price * quantity + plan.entry_fee)
    position = await session.scalar(
        select(RetailPosition).where(
            RetailPosition.account_id == account.id,
            RetailPosition.instrument_id == plan.instrument_id,
        ).with_for_update()
    )
    if position is None:
        position = RetailPosition(
            account_id=account.id, instrument_id=plan.instrument_id, quantity=quantity,
            average_cost=(cash_notional / quantity).quantize(PRICE, rounding=ROUND_HALF_UP),
            cost_basis=cash_notional, realized_pnl=ZERO,
        )
        session.add(position)
    else:
        new_qty = position.quantity + quantity
        new_cost = position.cost_basis + cash_notional
        position.quantity = new_qty
        position.cost_basis = new_cost
        position.average_cost = (new_cost / new_qty).quantize(PRICE, rounding=ROUND_HALF_UP)
    order = _filled_order(account, plan, "BUY", quantity, price, cash_notional, now, "Simulated automatic buy, with slippage and fee.")
    session.add(order)
    await session.flush()
    plan.entry_order_id = order.id
    session.add(RetailTransaction(
        account_id=account.id, entry_type="BUY", amount=-cash_notional, currency=account.base_currency,
        instrument_id=plan.instrument_id, occurred_at=now, source="paper",
        broker_reference=order.broker_order_id,
        description=f"Automatic buy of {quantity} {plan.ticker}, including a {plan.entry_fee} fee.",
    ))


async def _book_partial_sell(session, account, plan, scale, now):
    price = Decimal(scale["price"])
    quantity = Decimal(scale["quantity"])
    fee_paid = Decimal(scale["fee"])
    proceeds = money(price * quantity - fee_paid)
    position = await session.scalar(
        select(RetailPosition).where(
            RetailPosition.account_id == account.id,
            RetailPosition.instrument_id == plan.instrument_id,
        ).with_for_update()
    )
    if position is None or position.quantity < quantity:
        raise RuntimeError(f"Partial exit for {plan.ticker} exceeded the Invest position.")
    realized = money(proceeds - (position.average_cost * quantity))
    position.quantity = (position.quantity - quantity).quantize(QTY)
    position.cost_basis = money(position.average_cost * position.quantity)
    position.realized_pnl = money(position.realized_pnl + realized)
    if position.quantity <= 0:
        await session.delete(position)
    order = _filled_order(account, plan, "SELL", quantity, price, proceeds, now, "Sold half at the target.")
    session.add(order)
    await session.flush()
    session.add(RetailTransaction(
        account_id=account.id, entry_type="SELL", amount=proceeds, currency=account.base_currency,
        instrument_id=plan.instrument_id, occurred_at=now, source="paper",
        broker_reference=order.broker_order_id,
        description=f"Automatic sale of {quantity} {plan.ticker} at the target. The remainder stays open.",
    ))
    return realized


async def _book_sell(session, account, plan, now):
    price = Decimal(plan.exit_price)
    quantity = Decimal(plan.quantity)
    proceeds = money(price * quantity - plan.exit_fee)
    position = await session.scalar(
        select(RetailPosition).where(
            RetailPosition.account_id == account.id,
            RetailPosition.instrument_id == plan.instrument_id,
        ).with_for_update()
    )
    if position is None or position.quantity < quantity:
        raise RuntimeError(f"Automatic exit for {plan.ticker} exceeded the Invest position.")
    realized = money(proceeds - (position.average_cost * quantity))
    position.quantity = (position.quantity - quantity).quantize(QTY)
    position.cost_basis = money(position.average_cost * position.quantity)
    position.realized_pnl = money(position.realized_pnl + realized)
    if position.quantity <= 0:
        await session.delete(position)
    order = _filled_order(account, plan, "SELL", quantity, price, proceeds, now, f"Simulated automatic sell ({plan.exit_reason}).")
    session.add(order)
    await session.flush()
    plan.exit_order_id = order.id
    session.add(RetailTransaction(
        account_id=account.id, entry_type="SELL", amount=proceeds, currency=account.base_currency,
        instrument_id=plan.instrument_id, occurred_at=now, source="paper",
        broker_reference=order.broker_order_id,
        description=f"Automatic sell of {quantity} {plan.ticker}. {plan.exit_reason or ''}".strip(),
    ))
    return realized


def _filled_order(account, plan, side, quantity, price, notional, now, warning):
    return RetailOrder(
        user_id=account.user_id, account_id=account.id, instrument_id=plan.instrument_id,
        side=side, order_type="limit", quantity=quantity, notional=notional, limit_price=plan.limit_price,
        status="FILLED", submitted_at=plan.submitted_at or now, filled_at=now,
        average_fill_price=price.quantize(PRICE, rounding=ROUND_HALF_UP), filled_quantity=quantity,
        broker_provider=account.broker_provider, broker_order_id=str(uuid4()),
        origin="automatic", warnings=[warning],
    )


def _buy(book, plan, price, quoted_at, now):
    cost = money(price * plan.quantity + fee(price * plan.quantity, POLICY))
    _release(book, plan)
    book.cash = money(book.cash - cost)
    plan.entry_price = price
    plan.entry_fee = fee(price * plan.quantity, POLICY)
    plan.status = "open"
    plan.opened_at = now
    plan.entry_quote_at = quoted_at
    plan.mark_price = price
    plan.mark_as_of = quoted_at


def _scale_plan(book, plan, price, quoted_at, now) -> bool:
    if (plan.evidence or {}).get("scaled"):
        return False
    quantity = Decimal(plan.quantity)
    sold = (quantity / 2).quantize(QTY, rounding=ROUND_FLOOR)
    remaining = quantity - sold
    entry = plan.entry_price or plan.limit_price
    stop = min(entry, plan.limit_price - CENT)
    if sold <= 0 or remaining <= 0 or not ZERO < stop < plan.limit_price:
        return False
    available = plan.available_quantity
    if available is not None:
        sold = min(sold, Decimal(available))
        if sold <= 0 or quantity - sold <= 0:
            return False
    exit_fee = fee(price * sold, POLICY)
    allocated_entry = money(plan.entry_fee * sold / quantity)
    proceeds = money(price * sold - exit_fee)
    realized = money((price - entry) * sold - allocated_entry - exit_fee)
    book.cash = money(book.cash + proceeds)
    book.realized_pnl = money(book.realized_pnl + realized)
    plan.entry_fee = money(plan.entry_fee - allocated_entry)
    plan.quantity = quantity - sold
    plan.stop_price = stop
    plan.realized_pnl = money((plan.realized_pnl or ZERO) + realized)
    plan.exit_fee = money((plan.exit_fee or ZERO) + exit_fee)
    plan.evidence = {**(plan.evidence or {}), "scaled": True, "pending_scale": {
        "quantity": str(sold), "price": str(price), "fee": str(exit_fee), "at": utc(now).isoformat(),
    }}
    plan.exit_reason = "Sold half at the target. The stop on the remainder is at the entry price."
    plan.mark_price = price
    plan.mark_as_of = quoted_at
    return True


def _sell(book, plan, price, quoted_at, now, reason):
    available = plan.available_quantity
    sold = Decimal(plan.quantity) if available is None else min(Decimal(plan.quantity), Decimal(available))
    if sold <= 0:
        plan.status = "closed"
        plan.closed_at = now
        plan.exit_reason = "Position was closed outside the automatic plan."
        plan.exit_price = None
        return
    if sold != Decimal(plan.quantity):
        plan.evidence = {**(plan.evidence or {}), "planned_quantity": str(plan.quantity)}
        plan.quantity = sold
    exit_fee = fee(price * sold, POLICY)
    proceeds = money(price * sold - exit_fee)
    entry = plan.entry_price or plan.limit_price
    realized = money((price - entry) * sold - plan.entry_fee - exit_fee)
    book.cash = money(book.cash + proceeds)
    book.realized_pnl = money(book.realized_pnl + realized)
    plan.exit_price = price
    plan.exit_fee = exit_fee
    plan.realized_pnl = realized
    plan.status = "closed"
    plan.closed_at = now
    plan.exit_quote_at = quoted_at
    plan.exit_reason = reason


def _cancel(book, plan, status, reason):
    if plan.status != "pending":
        return
    _release(book, plan)
    plan.status = status
    plan.exit_reason = reason[:255]


def _release(book, plan):
    if plan.reserved_cash:
        book.reserved_cash = money(book.reserved_cash - plan.reserved_cash)
        plan.reserved_cash = ZERO


def _fill_allowed(book, plans, holdings, plan, price) -> bool:
    equity = _equity(book, plans, holdings)
    cost = money(price * plan.quantity + fee(price * plan.quantity, POLICY))
    other_reserved = book.reserved_cash - (plan.reserved_cash or ZERO)
    floor = equity * Decimal(POLICY["cash_reserve_pct"]) / 100
    if cost > book.cash - other_reserved - floor or cost > book.cash:
        return False
    sector_used = _sector_used(plans, holdings, plan.sector, plan)
    position_used = _position_used(plans, holdings, plan)
    stop_fill = (plan.stop_price * (1 - Decimal(POLICY["slippage_bps"]) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
    planned = (price - stop_fill) * plan.quantity + fee(price * plan.quantity, POLICY) + fee(stop_fill * plan.quantity, POLICY)
    active = _active_ids(plans, holdings)
    return not (
        len(active) > POLICY["max_positions"]
        or cost + position_used > equity * Decimal(str(position_cap(POLICY, plan.asset_class))) / 100
        or cost + sector_used > equity * Decimal(POLICY["max_sector_pct"]) / 100
        or planned > equity * Decimal(str(POLICY["risk_per_trade_pct"])) / 100
        or _aggregate_risk(plans) > equity * Decimal(str(POLICY["max_aggregate_risk_pct"])) / 100
    )


def _latch_drawdown(book, plans, holdings, blockers):
    if not book.marks_reliable:
        return
    equity = _equity(book, plans, holdings)
    if equity <= 0:
        return
    if book.high_water_equity is None or book.high_water_equity <= 0:
        book.high_water_equity = equity
        return
    if equity > book.high_water_equity:
        book.high_water_equity = equity
    drawdown = max(ZERO, (1 - equity / book.high_water_equity) * 100)
    book.max_drawdown_pct = max(book.max_drawdown_pct, drawdown)
    if drawdown < Decimal(POLICY["max_drawdown_pct"]) or book.halt_reason:
        return
    if book.trading_mode != "automatic":
        blockers.append(
            f"Drawdown is {drawdown.quantize(CENT)}% against the {POLICY['max_drawdown_pct']}% limit. "
            "Automatic mode would halt and liquidate."
        )
        return
    book.halt_reason = f"{POLICY['max_drawdown_pct']}% peak-to-trough drawdown limit reached; automatic liquidation."
    book.automation_status = "halted"
    for plan in plans:
        if plan.status == "pending":
            _cancel(book, plan, "cancelled", book.halt_reason)


def _equity(book, plans, holdings):
    covered = {plan.instrument_id for plan in plans if plan.status == "open"}
    invested = sum(
        ((plan.mark_price or plan.entry_price or plan.limit_price) * Decimal(plan.quantity)
         for plan in plans if plan.status == "open"),
        ZERO,
    )
    invested += sum((holding.market_value for holding in holdings if holding.instrument_id not in covered), ZERO)
    return money(book.cash + invested)


def _active_ids(plans, holdings):
    ids = {plan.instrument_id for plan in plans if plan.status in {"pending", "open"}}
    ids.update(holding.instrument_id for holding in holdings)
    return ids


def _sector_used(plans, holdings, sector, skip):
    total = sum(
        ((plan.mark_price or plan.entry_price or plan.limit_price) * Decimal(plan.quantity)
         for plan in plans if plan is not skip and plan.status in {"pending", "open"} and plan.sector == sector),
        ZERO,
    )
    total += sum((holding.market_value for holding in holdings if holding.sector == sector), ZERO)
    return total


def _position_used(plans, holdings, plan):
    total = sum(
        ((other.mark_price or other.entry_price or other.limit_price) * Decimal(other.quantity)
         for other in plans if other is not plan and other.status in {"pending", "open"} and other.instrument_id == plan.instrument_id),
        ZERO,
    )
    total += sum((holding.market_value for holding in holdings if holding.instrument_id == plan.instrument_id), ZERO)
    return total


def _aggregate_risk(plans):
    total = ZERO
    for plan in plans:
        if plan.status not in {"pending", "open"}:
            continue
        price = plan.entry_price or plan.limit_price
        stop_fill = (plan.stop_price * (1 - Decimal(POLICY["slippage_bps"]) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
        total += max(ZERO, (price - stop_fill) * Decimal(plan.quantity) + fee(price * Decimal(plan.quantity), POLICY) + fee(stop_fill * Decimal(plan.quantity), POLICY))
    return total


def _daily_loss(plans, equity, now):
    if equity <= 0:
        return False
    day = utc(now).astimezone(NEW_YORK).date()
    losses = sum(
        (-min(plan.realized_pnl or ZERO, ZERO) for plan in plans
         if plan.closed_at is not None and utc(plan.closed_at).astimezone(NEW_YORK).date() == day),
        ZERO,
    )
    return losses >= equity * Decimal(str(POLICY["max_daily_loss_pct"])) / 100


def _reserved(plans) -> Decimal:
    return money(sum((plan.reserved_cash or ZERO for plan in plans if plan.status == "pending"), ZERO))


def _slip_buy(price: Decimal) -> Decimal:
    return (price * (1 + Decimal(POLICY["slippage_bps"]) / 10000)).quantize(CENT, rounding=ROUND_CEILING)


def _slip_sell(price: Decimal) -> Decimal:
    return (price * (1 - Decimal(POLICY["slippage_bps"]) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
