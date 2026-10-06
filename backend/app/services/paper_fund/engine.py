"""Transactional paper execution with cash reservation and automatic exits.

No external orders are sent. Each fill requires a verified, later observation;
last-price simulation includes adverse slippage and fees, but not an order book.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.paper_fund import (
    PaperEquityResponse, PaperFundResponse, PaperOrderResponse, PaperRunResponse, PaperStart,
)
from app.core.auth import AuthenticatedUser
from app.db.locks import lock_idempotency_scope, lock_portfolio
from app.models import Instrument, InstrumentQuote, PaperEquitySnapshot, PaperFundRun, PaperOrder, Position, RadarRun, RadarSnapshot
from app.services.portfolio.operating_core import get_or_create_default_portfolio, get_dashboard, load_dashboard_state
from app.services.paper_fund.capital import bind_book, book_fills, capital_policy, load_book
from app.services.market_radar.execution import MAX_SIGNAL_AGE_SECONDS, execution_rejection, quote_rejection
from app.services.paper_fund.calendar import market_blocker

ZERO = Decimal("0")
CENT = Decimal("0.01")
POLICY = {
    "version": 1, "max_position_pct": 10, "risk_per_trade_pct": 0.5,
    "max_positions": 5, "cash_reserve_pct": 20, "max_drawdown_pct": 5,
    "max_sector_pct": 20, "stop_loss_pct": 3, "take_profit_pct": 6,
    "slippage_bps": 10, "fee_bps": 5, "quote_max_age_seconds": 120,
    "order_ttl_minutes": 30,
}
SIMULATION_NOTICE = (
    "Capital trades currently use simulated execution; no live broker orders. Whole-share, long-only momentum strategy, "
    "not a validated profit forecast. Fills use later observed prices with 10 bps adverse slippage "
    "and 5 bps fees per side. Order-book depth, queue priority, partial fills, dividends and corporate "
    "actions are not simulated. Moves between observations can be missed. Stops can fill below their "
    "trigger. Missing or stale data blocks execution."
)


class PaperFundError(ValueError):
    pass


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fee(notional: Decimal, policy: dict) -> Decimal:
    return (notional * Decimal(str(policy["fee_bps"])) / 10000).quantize(CENT, rounding=ROUND_CEILING)


def reservation(order: PaperOrder, policy: dict) -> Decimal:
    value = order.limit_price * order.quantity
    return value + fee(value, policy)


def accounting(run: PaperFundRun, orders: list[PaperOrder]) -> dict:
    opened = [o for o in orders if o.status == "open"] + getattr(run, "_external_holdings", [])
    invested = money(sum(((o.mark_price or o.entry_price) * o.quantity for o in opened), ZERO))
    unrealized = money(sum((((o.mark_price or o.entry_price) - o.entry_price) * o.quantity - o.entry_fee
                            for o in opened), ZERO))
    realized = money(sum((o.realized_pnl for o in orders if o.status == "closed"), ZERO))
    reserved = money(sum((reservation(o, run.policy) for o in orders if o.status == "pending"), ZERO))
    equity = money(run.cash_balance + invested)
    return {
        "equity": equity, "realized_pnl": realized, "unrealized_pnl": unrealized,
        "reserved_cash": reserved, "available_cash": money(run.cash_balance - reserved),
        "total_pnl": money(equity - run.starting_cash),
        "return_pct": ((equity / run.starting_cash - 1) * 100).quantize(Decimal("0.0001")),
        "fees_paid": money(sum((o.entry_fee + o.exit_fee for o in orders), ZERO)),
    }


def size_order(run: PaperFundRun, orders: list[PaperOrder], price: Decimal, sector: str | None) -> tuple[int, Decimal, Decimal, Decimal]:
    """Round down to whole shares; reserve fees, risk budget and sector capacity."""
    policy = run.policy
    state = accounting(run, orders)
    equity = state["equity"]
    active = [o for o in orders if o.status in {"open", "pending"}] + getattr(run, "_external_holdings", [])
    limit = (price * (1 + Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
    stop = (limit * (1 - Decimal(str(policy["stop_loss_pct"])) / 100)).quantize(CENT, rounding=ROUND_FLOOR)
    target = (limit * (1 + Decimal(str(policy["take_profit_pct"])) / 100)).quantize(CENT, rounding=ROUND_CEILING)
    if len(active) >= policy["max_positions"] or equity <= 0 or not ZERO < stop < limit < target:
        return 0, limit, stop, target
    sector_used = sum(((o.mark_price or o.limit_price) * o.quantity for o in active if o.sector == sector), ZERO)
    cash_budget = state["available_cash"] - equity * Decimal(str(policy["cash_reserve_pct"])) / 100
    sector_budget = equity * Decimal(str(policy["max_sector_pct"])) / 100 - sector_used
    budget = min(cash_budget, equity * Decimal(str(policy["max_position_pct"])) / 100, sector_budget)
    risk_budget = equity * Decimal(str(policy["risk_per_trade_pct"])) / 100
    # Include modeled stop slippage and both execution fees in planned risk.
    stop_fill = (stop * (1 - Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
    risk_per_share = limit - stop_fill + (limit + stop_fill) * Decimal(str(policy["fee_bps"])) / 10000
    quantity = max(0, int(min(budget / limit, risk_budget / risk_per_share)))
    while quantity and (quantity * limit + fee(quantity * limit, policy) > budget
                        or quantity * (limit - stop_fill) + fee(quantity * limit, policy)
                        + fee(quantity * stop_fill, policy) > risk_budget):
        quantity -= 1
    return quantity, limit, stop, target


def _cancel_pending(orders: list[PaperOrder], reason: str) -> None:
    for order in orders:
        if order.status == "pending":
            order.status = "cancelled"
            order.exit_reason = reason


def _update_drawdown(run: PaperFundRun, orders: list[PaperOrder]) -> Decimal:
    equity = accounting(run, orders)["equity"] - getattr(run, "_net_flow_since_start", ZERO)
    run.high_water_equity = max(run.high_water_equity, equity)
    drawdown = max(ZERO, (1 - equity / run.high_water_equity) * 100)
    run.max_drawdown_pct = max(run.max_drawdown_pct, drawdown)
    return drawdown


def _position_quote_rejection(order: PaperOrder, quote: InstrumentQuote | None, now: datetime) -> str | None:
    error = quote_rejection(quote, now)
    if error:
        return error
    if order.mark_as_of is not None and utc(quote.as_of) < utc(order.mark_as_of):
        return "The quote predates the position's latest mark."
    return None


def process_orders(run: PaperFundRun, orders: list[PaperOrder], quotes: dict, now: datetime,
                   *, automatic_execution: bool = True) -> list[str]:
    """Pure state transition used by the locked service and deterministic tests."""
    now = utc(now)
    policy = run.policy
    blockers: list[str] = []
    if run.status == "completed":
        return blockers
    session_error = market_blocker(now)
    if session_error:
        blockers.append(session_error)
    if automatic_execution and now >= utc(run.ends_at) and run.status != "halted":
        run.status = "liquidating"
    if run.status != "running":
        _cancel_pending(orders, f"Run {run.status}; entry cancelled.")
    for order in orders:
        if order.status == "pending" and now >= utc(order.expires_at):
            order.status = "expired"
            order.exit_reason = "Entry limit expired without a fill."
        if order.status != "open":
            continue
        quote = quotes.get(order.instrument_id)
        error = _position_quote_rejection(order, quote, now)
        if error:
            blockers.append(f"{order.ticker}: {error} Holding last available mark; exit awaits valid data.")
        elif not session_error and (order.mark_as_of is None or utc(quote.as_of) >= utc(order.mark_as_of)):
            order.mark_price = quote.price
            order.mark_as_of = quote.as_of
    drawdown = _update_drawdown(run, orders)
    if drawdown >= Decimal(str(policy["max_drawdown_pct"])) and not run.halt_reason:
        run.halt_reason = f"{policy['max_drawdown_pct']}% peak-to-trough drawdown limit reached; automatic liquidation."
        run.status = "halted"
        _cancel_pending(orders, run.halt_reason)
    for order in orders:
        if order.status != "open" or session_error or not automatic_execution:
            continue
        quote = quotes.get(order.instrument_id)
        if _position_quote_rejection(order, quote, now) or utc(quote.as_of) <= utc(order.entry_quote_at):
            continue
        reason = None
        if run.status in {"liquidating", "halted"}:
            reason = "drawdown_halt" if run.halt_reason else "review_period_ended"
        elif quote.price <= order.stop_price:
            reason = "stop_loss"
        elif quote.price >= order.target_price:
            reason = "take_profit"
        if reason is None:
            continue
        price = (quote.price * (1 - Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
        # A profit-target limit cannot fill below its limit after costs of crossing.
        if reason == "take_profit" and price < order.target_price:
            continue
        order.exit_price = max(CENT, price)
        order.exit_fee = fee(order.exit_price * order.quantity, policy)
        run.cash_balance = money(run.cash_balance + order.exit_price * order.quantity - order.exit_fee)
        order.realized_pnl = money((order.exit_price - order.entry_price) * order.quantity - order.entry_fee - order.exit_fee)
        order.status = "closed"
        order.closed_at = now
        order.exit_quote_at = quote.as_of
        order.exit_reason = reason
    # Any unreliable open mark stops new risk, but never disables exit processing.
    uncertain_marks = getattr(run, "_external_marks_unreliable", False) or any(_position_quote_rejection(o, quotes.get(o.instrument_id), now) for o in orders if o.status == "open")
    for order in orders:
        if order.status != "pending" or run.status != "running" or session_error or uncertain_marks or not automatic_execution:
            continue
        quote = quotes.get(order.instrument_id)
        error = quote_rejection(quote, now)
        if error:
            blockers.append(f"{order.ticker}: {error}")
            continue
        # Never fill from the quote that generated the order (no look-ahead).
        if utc(quote.as_of) <= utc(order.submitted_at):
            continue
        if quote.price <= order.stop_price:
            order.status = "cancelled"
            order.exit_reason = "Signal invalidated below planned stop before entry."
            continue
        price = (quote.price * (1 + Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_CEILING)
        if price > order.limit_price:
            continue
        state = accounting(run, orders)
        cost = price * order.quantity + fee(price * order.quantity, policy)
        other_reserved = state["reserved_cash"] - reservation(order, policy)
        reserve_floor = state["equity"] * Decimal(str(policy["cash_reserve_pct"])) / 100
        sector_used = sum(((o.mark_price or o.limit_price) * o.quantity for o in orders + getattr(run, "_external_holdings", [])
                           if o is not order and o.status in {"pending", "open"} and o.sector == order.sector), ZERO)
        stop_fill = (order.stop_price * (1 - Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
        planned_loss = (price - stop_fill) * order.quantity + fee(price * order.quantity, policy) + fee(stop_fill * order.quantity, policy)
        if (cost > run.cash_balance - other_reserved - reserve_floor
                or cost > state["equity"] * Decimal(str(policy["max_position_pct"])) / 100
                or cost + sector_used > state["equity"] * Decimal(str(policy["max_sector_pct"])) / 100
                or planned_loss > state["equity"] * Decimal(str(policy["risk_per_trade_pct"])) / 100):
            order.status = "cancelled"
            order.exit_reason = "Capital or concentration limit changed before fill."
            continue
        order.entry_price = price
        order.entry_fee = fee(price * order.quantity, policy)
        run.cash_balance = money(run.cash_balance - cost)
        order.status = "open"
        order.opened_at = now
        order.entry_quote_at = quote.as_of
        order.mark_price = quote.price
        order.mark_as_of = quote.as_of
    if _update_drawdown(run, orders) >= Decimal(str(policy["max_drawdown_pct"])) and not run.halt_reason:
        run.halt_reason = f"{policy['max_drawdown_pct']}% drawdown limit reached after execution costs; automatic liquidation."
        run.status = "halted"
        _cancel_pending(orders, run.halt_reason)
    if run.status in {"liquidating", "halted"} and not any(o.status == "open" for o in orders):
        # Keep a risk halt latched until the experiment ends, even when flat.
        if run.status == "liquidating" or now >= utc(run.ends_at):
            run.status = "completed"
            run.completed_at = now
    return list(dict.fromkeys(blockers))


async def _latest(session: AsyncSession, owner: str, *, lock: bool = False,
                  read_lock: bool = False, run_id: UUID | None = None) -> PaperFundRun | None:
    stmt = select(PaperFundRun).where(PaperFundRun.owner_user_id == owner)
    if run_id is not None:
        stmt = stmt.where(PaperFundRun.id == run_id)
    stmt = stmt.order_by(PaperFundRun.started_at.desc()).limit(1)
    if lock:
        stmt = stmt.with_for_update()
    elif read_lock:
        stmt = stmt.with_for_update(read=True)
    return await session.scalar(stmt.execution_options(populate_existing=True))


async def _orders(session: AsyncSession, run: PaperFundRun) -> list[PaperOrder]:
    return list(await session.scalars(select(PaperOrder).where(PaperOrder.run_id == run.id)
                                      .order_by(PaperOrder.submitted_at).execution_options(populate_existing=True)))


async def _snapshot(session: AsyncSession, run: PaperFundRun, orders: list[PaperOrder], now: datetime, *, force=False, book=None) -> None:
    last = await session.scalar(select(PaperEquitySnapshot).where(PaperEquitySnapshot.run_id == run.id)
                                .order_by(PaperEquitySnapshot.recorded_at.desc()).limit(1))
    if not force and last and now - utc(last.recorded_at) < timedelta(minutes=5):
        return
    state = book.state if book else accounting(run, orders)
    session.add(PaperEquitySnapshot(
        run_id=run.id, recorded_at=now, equity=state["equity"], cash_balance=run.cash_balance,
        realized_pnl=state["realized_pnl"], unrealized_pnl=state["unrealized_pnl"],
        drawdown_pct=max(ZERO, (1 - (state["equity"] - getattr(run, "_net_flow_since_start", ZERO)) / run.high_water_equity) * 100),
    ))


async def _portfolio(session, owner, *, read=False):
    portfolio = await get_or_create_default_portfolio(session, AuthenticatedUser(id=owner, email=None))
    return await lock_portfolio(session, portfolio, read=read)


async def attach_to_capital(session, portfolio, run, orders):
    """Preserve an existing run and book its fills, without adding any capital."""
    if run.portfolio_id is not None:
        if run.portfolio_id != portfolio.id:
            raise PaperFundError("Execution account does not match Capital.")
        return
    await book_fills(session, portfolio, orders)
    book = await load_book(session, portfolio)
    run.portfolio_id = portfolio.id
    run.net_contributions_at_start = book.net_contributions
    run.cash_balance = book.cash
    portfolio.trading_mode = "automatic" if run.status in {"running", "liquidating", "halted"} else "manual"
    await session.flush()


async def start_run(session: AsyncSession, owner: str, payload: PaperStart, *, now: datetime | None = None,
                    idempotency_key: str | None = None, resume: bool = False) -> PaperFundResponse:
    now = utc(now or datetime.now(timezone.utc))
    # Seed only genuinely new accounts before taking transaction-scoped locks.
    portfolio = await get_or_create_default_portfolio(session, AuthenticatedUser(id=owner, email=None))
    await lock_idempotency_scope(session, "paper-fund-start", owner)
    portfolio = await lock_portfolio(session, portfolio)
    if portfolio.base_currency != "USD":
        raise PaperFundError("Automatic execution currently requires a USD Capital account.")
    if idempotency_key:
        prior = await session.scalar(select(PaperFundRun).where(
            PaperFundRun.owner_user_id == owner, PaperFundRun.start_key == idempotency_key))
        if prior is not None:
            await session.commit()
            return await overview(session, owner, now=now, run_id=prior.id)
    run = await _latest(session, owner, lock=True)
    if run is None or run.status == "completed":
        book = await load_book(session, portfolio)
        if book.state["equity"] <= 0:
            raise PaperFundError("Capital must have positive equity before enabling automatic trading.")
        run = PaperFundRun(owner_user_id=owner, portfolio_id=portfolio.id,
            net_contributions_at_start=book.net_contributions, start_key=idempotency_key,
            status="running", starting_cash=book.state["equity"], cash_balance=book.cash,
            high_water_equity=book.state["equity"], max_drawdown_pct=ZERO,
            started_at=now, ends_at=now + timedelta(days=payload.duration_days),
            policy=await capital_policy(session, portfolio.id, POLICY),
            blockers=["Waiting for the automatic execution worker."], last_cycle_at=None,
            completed_at=None, halt_reason=None)
        session.add(run)
        portfolio.trading_mode = "automatic"
        await session.flush()
        await _snapshot(session, run, [], now, force=True, book=book)
    else:
        orders = await _orders(session, run)
        await attach_to_capital(session, portfolio, run, orders)
        if resume:
            if run.halt_reason:
                raise PaperFundError("The risk halt requires review; switching modes cannot override it.")
            run.status = "running" if now < utc(run.ends_at) else "liquidating"
            portfolio.trading_mode = "automatic"
    await session.commit()
    return await overview(session, owner, now=now)


async def set_trading_mode(session, owner, mode):
    if mode == "automatic":
        return await start_run(session, owner, PaperStart(), resume=True)
    if mode != "manual":
        raise PaperFundError("Choose Manual or Automatic trading.")
    portfolio = await _portfolio(session, owner)
    run = await _latest(session, owner, lock=True)
    portfolio.trading_mode = "manual"
    if run is not None and run.status != "completed":
        orders = await _orders(session, run)
        if run.portfolio_id is None:
            await attach_to_capital(session, portfolio, run, orders)
            portfolio.trading_mode = "manual"
        if run.status == "running":
            run.status = "paused"
        _cancel_pending(orders, "Manual mode; automatic entry cancelled.")
    await session.commit()
    return await overview(session, owner)


async def control_run(session: AsyncSession, owner: str, action: str) -> PaperFundResponse:
    # Compatibility for existing clients. Mode is always stored on Capital.
    if action not in {"pause", "resume"}:
        raise PaperFundError("Unknown trading control.")
    return await set_trading_mode(session, owner, "manual" if action == "pause" else "automatic")


async def cycle(session: AsyncSession, owner: str, *, now: datetime | None = None) -> PaperFundResponse:
    # All Capital mutations use this same lock before touching execution state.
    portfolio = await _portfolio(session, owner)
    run = await _latest(session, owner, lock=True)
    now = utc(now or datetime.now(timezone.utc))
    if run is None:
        raise PaperFundError("Enable automatic trading first.")
    if run.portfolio_id is None:
        raise PaperFundError("Existing execution history must be attached to Capital before trading.")
    if run.status == "completed" or (run.last_cycle_at is not None and now < utc(run.last_cycle_at)):
        return await overview(session, owner, now=now)
    orders = await _orders(session, run)
    run.policy = await capital_policy(session, portfolio.id, run.policy)
    book = await load_book(session, portfolio)
    bind_book(run, orders, book)
    instrument_ids = {o.instrument_id for o in orders} | {p.instrument_id for p in book.positions}
    quotes = {q.instrument_id: q for q in await session.scalars(select(InstrumentQuote).where(
        InstrumentQuote.instrument_id.in_(instrument_ids)).execution_options(populate_existing=True))} if instrument_ids else {}
    external_errors = []
    for holding in run._external_holdings:
        quote = quotes.get(holding.instrument_id)
        error = quote_rejection(quote, now)
        if error:
            external_errors.append("An existing Capital holding lacks a fresh eligible quote; new automatic buys are blocked.")
        else:
            holding.mark_price = quote.price
    run._external_marks_unreliable = bool(external_errors)
    automatic = portfolio.trading_mode == "automatic"
    if not automatic:
        _cancel_pending(orders, "Manual mode; automatic entry cancelled.")
    before = [(o.id, o.status) for o in orders]
    blockers = process_orders(run, orders, quotes, now, automatic_execution=automatic)
    blockers.extend(external_errors)
    if not automatic:
        blockers.insert(0, "Manual mode: automatic buys and sells are stopped.")
    await book_fills(session, portfolio, orders)
    # The engine's validated marks update the shared position book as well.
    for position in await session.scalars(select(Position).where(Position.portfolio_id == portfolio.id, Position.quantity > 0)):
        quote = quotes.get(position.instrument_id)
        if not market_blocker(now) and not quote_rejection(quote, now):
            position.market_value = money(position.quantity * quote.price)
            position.unrealized_pnl = money((quote.price - position.average_cost) * position.quantity)
    await session.flush()
    book = await load_book(session, portfolio)
    bind_book(run, orders, book)
    if automatic and run.status == "running" and not market_blocker(now) and not external_errors:
        stale_held = any(_position_quote_rejection(o, quotes.get(o.instrument_id), now) for o in orders if o.status == "open")
        if not stale_held:
            await _queue_signals(session, run, orders, now, blockers)
    if run.status == "completed":
        portfolio.trading_mode = "manual"
    run.last_cycle_at = now
    run.blockers = list(dict.fromkeys(blockers))[:30]
    await session.flush()
    await _snapshot(session, run, orders, now, book=book,
                    force=before != [(o.id, o.status) for o in orders] or run.status == "completed")
    await session.commit()
    return await overview(session, owner, now=now)


async def _queue_signals(session: AsyncSession, run: PaperFundRun, orders: list[PaperOrder], now: datetime, blockers: list[str]) -> None:
    radar_run = await session.scalar(select(RadarRun).where(RadarRun.status == "completed", RadarRun.started_at <= now)
                                      .order_by(RadarRun.started_at.desc(), RadarRun.created_at.desc()).limit(1))
    if radar_run is None:
        blockers.append("Waiting for a completed market radar scan.")
        return
    rows = list((await session.execute(select(RadarSnapshot, Instrument, InstrumentQuote)
        .join(Instrument, Instrument.ticker == RadarSnapshot.ticker)
        .outerjoin(InstrumentQuote, InstrumentQuote.instrument_id == Instrument.id)
        .where(RadarSnapshot.run_id == radar_run.id)
        .where(RadarSnapshot.radar_priority.in_(["P0", "P1"]))
        .order_by(RadarSnapshot.priority_score.desc(), RadarSnapshot.ticker))).all())
    seen = {o.instrument_id for o in orders} | {p.instrument_id for p in getattr(run, "_external_holdings", [])}
    added = 0
    for snapshot, instrument, quote in rows:
        if instrument.id in seen:
            continue
        error = execution_rejection(snapshot, quote, now)
        if instrument.currency != "USD" or instrument.asset_class not in {"equity", "etf"}:
            error = "Instrument metadata does not match the USD equity mandate."
        if error:
            if len(blockers) < 25:
                blockers.append(f"{snapshot.ticker}: {error}")
            continue
        quantity, limit, stop, target = size_order(run, orders, quote.price, snapshot.sector)
        if quantity <= 0:
            blockers.append(f"{snapshot.ticker}: No capacity under cash, sector, position or risk limits.")
            continue
        order = PaperOrder(
            run_id=run.id, instrument_id=instrument.id, ticker=instrument.ticker, name=instrument.name,
            sector=snapshot.sector, status="pending", quantity=quantity,
            limit_price=limit, stop_price=stop, target_price=target,
            entry_fee=ZERO, exit_fee=ZERO, realized_pnl=ZERO,
            submitted_at=now, expires_at=min(now + timedelta(minutes=run.policy["order_ttl_minutes"]),
                                            utc(snapshot.as_of) + timedelta(seconds=MAX_SIGNAL_AGE_SECONDS),
                                            utc(snapshot.source_as_of) + timedelta(seconds=MAX_SIGNAL_AGE_SECONDS),
                                            utc(run.ends_at)),
            thesis=f"Confirmed positive radar momentum ({snapshot.change_pct}% session move), with measured liquidity and confirmation.",
            evidence={"radar_snapshot_id": str(snapshot.id), "radar_run_id": str(radar_run.id),
                      "quote_as_of": quote.as_of.isoformat(), "quote_source": quote.source,
                      "radar_evidence": snapshot.evidence, "policy_version": run.policy["version"]},
        )
        session.add(order)
        orders.append(order)
        seen.add(instrument.id)
        added += 1
    if not added and not any(o.status == "pending" for o in orders):
        blockers.append("No new radar signal currently passes every execution and capital check.")


async def overview(session: AsyncSession, owner: str, *, now: datetime | None = None, run_id: UUID | None = None) -> PaperFundResponse:
    now = utc(now or datetime.now(timezone.utc))
    # Keep cash, orders and history on the same committed state while a worker
    # fills orders. The request's session releases this read lock on close.
    user = AuthenticatedUser(id=owner, email=None)
    dashboard_state = await load_dashboard_state(session, user)
    portfolio = dashboard_state.portfolio
    run = await _latest(session, owner, run_id=run_id, read_lock=True)
    capital = await get_dashboard(session, user, state=dashboard_state)
    if run is None:
        return PaperFundResponse(generated_at=now, trading_mode=portfolio.trading_mode, capital=capital, run=None, orders=[], equity_history=[],
                                 blockers=["Choose Automatic to enable execution using this Capital account."],
                                 policy=POLICY, simulation_notice=SIMULATION_NOTICE)
    orders = await _orders(session, run)
    book = await load_book(session, portfolio, dashboard_state=dashboard_state)
    reserved = money(sum((reservation(o, run.policy) for o in orders if o.status == "pending"), ZERO))
    state = {**book.state, "reserved_cash": reserved, "available_cash": money(book.cash - reserved)}
    history = list(await session.scalars(select(PaperEquitySnapshot).where(PaperEquitySnapshot.run_id == run.id)
                                        .order_by(PaperEquitySnapshot.recorded_at)))
    if len(history) > 500:
        history = [history[round(i * (len(history) - 1) / 499)] for i in range(500)]
    blockers = list(run.blockers)
    if run.status != "completed":
        if run.last_cycle_at is None or now - utc(run.last_cycle_at) > timedelta(seconds=90):
            blockers.insert(0, "Execution worker has not checked this run in 90 seconds; automatic trading requires Celery worker and beat.")
        closed = market_blocker(now)
        if closed and closed not in blockers:
            blockers.insert(0, closed)
    return PaperFundResponse(
        generated_at=now, trading_mode=portfolio.trading_mode, capital=capital,
        run=PaperRunResponse(id=run.id, status=run.status, starting_cash=run.starting_cash,
            cash_balance=book.cash, max_drawdown_pct=run.max_drawdown_pct,
            started_at=run.started_at, ends_at=run.ends_at, last_cycle_at=run.last_cycle_at,
            completed_at=run.completed_at, halt_reason=run.halt_reason, **state),
        orders=[PaperOrderResponse(id=o.id, ticker=o.ticker, name=o.name, status=o.status,
            quantity=o.quantity, limit_price=o.limit_price, stop_price=o.stop_price, target_price=o.target_price,
            entry_price=o.entry_price, exit_price=o.exit_price, mark_price=o.mark_price,
            realized_pnl=o.realized_pnl, fees_paid=o.entry_fee + o.exit_fee,
            created_at=o.submitted_at, expires_at=o.expires_at, opened_at=o.opened_at,
            closed_at=o.closed_at, exit_reason=o.exit_reason, thesis=o.thesis) for o in orders],
        equity_history=[PaperEquityResponse.model_validate(s) for s in history],
        blockers=list(dict.fromkeys(blockers)), policy=run.policy, simulation_notice=SIMULATION_NOTICE,
    )
