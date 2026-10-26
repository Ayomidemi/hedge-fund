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
from app.models import Instrument, InstrumentQuote, PaperCycleEvent, PaperEquitySnapshot, PaperFundRun, PaperOrder, Position, RadarRun, RadarSnapshot
from app.services.paper_fund.eligibility import instrument_rejection
from app.services.paper_fund.reentry import reentry_rejection
from app.services.portfolio.operating_core import get_or_create_default_portfolio, get_dashboard, load_dashboard_state
from app.services.paper_fund.capital import bind_book, book_fills, capital_policy, load_book
from app.services.market_radar.execution import MAX_SIGNAL_AGE_SECONDS, execution_rejection, quote_rejection
from app.services.paper_fund.calendar import market_blocker
from app.services.risk.policy import profile_policy, position_cap

ZERO = Decimal("0")
CENT = Decimal("0.01")
POLICY = profile_policy("medium")
SIMULATION_NOTICE = (
    "Capital trades currently use simulated execution; no live broker orders. Whole-share long momentum, plus at most one SPY hedge, "
    "not a validated profit forecast. Fills use later observed prices with 10 bps adverse slippage "
    "and 5 bps fees per side. Tiingo derived reference prices may be used for paper fills; they are not executable exchange bids or offers. "
    "A profit target sells half the position once. Order-book depth, queue priority, dividends and corporate "
    "actions are not simulated. Earnings calendars are not connected. Moves between observations can be missed. Stops can fill below their "
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


def _short(order) -> bool:
    return (getattr(order, "direction", None) or "long") == "short"


def reservation(order: PaperOrder, policy: dict) -> Decimal:
    if _short(order):
        return ZERO
    value = order.limit_price * order.quantity
    return value + fee(value, policy)


def cover_reserve(order: PaperOrder, policy: dict) -> Decimal:
    """Cash an open short needs to buy the shares back at its stop."""
    if not _short(order) or order.status != "open":
        return ZERO
    slip = Decimal(str(policy["slippage_bps"])) / 10000
    stop_fill = (order.stop_price * (1 + slip)).quantize(CENT, rounding=ROUND_CEILING)
    return money(stop_fill * order.quantity + fee(stop_fill * order.quantity, policy))


def accounting(run: PaperFundRun, orders: list[PaperOrder]) -> dict:
    opened = [o for o in orders if o.status == "open"] + getattr(run, "_external_holdings", [])

    def _invested(order):
        value = (order.mark_price or order.entry_price) * order.quantity
        return -value if _short(order) else value

    def _unrealized(order):
        mark = order.mark_price or order.entry_price
        if _short(order):
            return (order.entry_price - mark) * order.quantity - order.entry_fee
        return (mark - order.entry_price) * order.quantity - order.entry_fee

    invested = money(sum((_invested(o) for o in opened), ZERO))
    unrealized = money(sum((_unrealized(o) for o in opened), ZERO))
    realized = money(sum((o.realized_pnl for o in orders if o.status in {"open", "closed"}), ZERO))
    reserved = money(sum((reservation(o, run.policy) for o in orders if o.status == "pending"), ZERO)
                     + sum((cover_reserve(o, run.policy) for o in orders), ZERO))
    equity = money(run.cash_balance + invested)
    return {
        "equity": equity, "realized_pnl": realized, "unrealized_pnl": unrealized,
        "reserved_cash": reserved, "available_cash": money(run.cash_balance - reserved),
        "total_pnl": money(equity - run.starting_cash),
        "return_pct": ((equity / run.starting_cash - 1) * 100).quantize(Decimal("0.0001")),
        "fees_paid": money(sum((o.entry_fee + o.exit_fee for o in orders), ZERO)),
    }


def _scale_long(run, order, price: Decimal, now: datetime) -> bool:
    """Sell half at the target and leave the remainder open with the stop at entry."""
    if (order.evidence or {}).get("scaled") or order.quantity < 2:
        return False
    sold = order.quantity // 2
    remaining = order.quantity - sold
    entry = order.entry_price or order.limit_price
    stop = min(entry, order.limit_price - CENT)
    if sold < 1 or remaining < 1 or not ZERO < stop < order.limit_price:
        return False
    policy = run.policy
    exit_fee = fee(price * sold, policy)
    allocated_entry = money(order.entry_fee * Decimal(sold) / Decimal(order.quantity))
    run.cash_balance = money(run.cash_balance + price * sold - exit_fee)
    order.realized_pnl = money(order.realized_pnl + (price - entry) * sold - allocated_entry - exit_fee)
    order.entry_fee = money(order.entry_fee - allocated_entry)
    order.quantity = remaining
    order.stop_price = stop
    slices = list((order.evidence or {}).get("scale_outs") or [])
    slices.append({"quantity": sold, "price": str(price), "fee": str(exit_fee), "at": utc(now).isoformat(), "reason": "take_profit"})
    order.evidence = {**(order.evidence or {}), "scale_outs": slices, "scaled": True}
    order.exit_reason = "Sold half at the target. The stop on the remainder is at the entry price."
    return True


def size_order(run: PaperFundRun, orders: list[PaperOrder], price: Decimal, sector: str | None, asset_class: str = "equity") -> tuple[int, Decimal, Decimal, Decimal]:
    """Round down to whole shares; reserve fees, risk budget and sector capacity."""
    policy = run.policy
    state = accounting(run, orders)
    equity = state["equity"]
    active = [o for o in orders if o.status in {"open", "pending"} and not _short(o)] + getattr(run, "_external_holdings", [])
    limit = (price * (1 + Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
    stop = (limit * (1 - Decimal(str(policy["stop_loss_pct"])) / 100)).quantize(CENT, rounding=ROUND_FLOOR)
    target = (limit * (1 + Decimal(str(policy["take_profit_pct"])) / 100)).quantize(CENT, rounding=ROUND_CEILING)
    if len(active) >= policy["max_positions"] or equity <= 0 or not ZERO < stop < limit < target:
        return 0, limit, stop, target
    sector_used = sum(((o.mark_price or o.limit_price) * o.quantity for o in active if o.sector == sector), ZERO)
    cash_budget = state["available_cash"] - equity * Decimal(str(policy["cash_reserve_pct"])) / 100
    sector_budget = equity * Decimal(str(policy["max_sector_pct"])) / 100 - sector_used
    budget = min(cash_budget, equity * Decimal(str(position_cap(policy, asset_class))) / 100, sector_budget)
    risk_budget = equity * Decimal(str(policy["risk_per_trade_pct"])) / 100
    if "max_aggregate_risk_pct" in policy:
        risk_budget = min(risk_budget, max(ZERO, equity * Decimal(str(policy["max_aggregate_risk_pct"])) / 100 - aggregate_risk(run, orders)))
    # Include modeled stop slippage and both execution fees in planned risk.
    stop_fill = (stop * (1 - Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
    risk_per_share = limit - stop_fill + (limit + stop_fill) * Decimal(str(policy["fee_bps"])) / 10000
    quantity = max(0, int(min(budget / limit, risk_budget / risk_per_share)))
    while quantity and (quantity * limit + fee(quantity * limit, policy) > budget
                        or quantity * (limit - stop_fill) + fee(quantity * limit, policy)
                        + fee(quantity * stop_fill, policy) > risk_budget):
        quantity -= 1
    return quantity, limit, stop, target


def aggregate_risk(run, orders):
    total = ZERO
    for order in [o for o in orders if o.status in {"open", "pending"}] + getattr(run, "_external_holdings", []):
        price = order.limit_price if order.status == "pending" else (order.mark_price or order.entry_price)
        stop = getattr(order, "stop_price", ZERO)
        slip = Decimal(str(run.policy["slippage_bps"])) / 10000
        if _short(order):
            stop_fill = (stop * (1 + slip)).quantize(CENT, rounding=ROUND_CEILING)
            loss = max(ZERO, stop_fill - price)
        else:
            stop_fill = (stop * (1 - slip)).quantize(CENT, rounding=ROUND_FLOOR)
            loss = max(ZERO, price - stop_fill)
        total += loss * order.quantity + fee(price * order.quantity, run.policy) + fee(stop_fill * order.quantity, run.policy)
    return total


def daily_loss_blocker(run, orders, now):
    if "max_daily_loss_pct" not in run.policy:
        return None
    from app.services.paper_fund.calendar import NEW_YORK
    day = now.astimezone(NEW_YORK).date().isoformat()
    equity = accounting(run, orders)["equity"] - getattr(run, "_net_flow_since_start", ZERO)
    state = dict(getattr(run, "risk_state", None) or {})
    if state.get("day") != day:
        state = {"day": day, "baseline": state.get("last_equity", str(equity)), "blocked": False}
    baseline = Decimal(state["baseline"])
    loss = max(ZERO, (baseline - equity) / baseline * 100) if baseline > 0 else ZERO
    state.update(last_equity=str(equity), loss_pct=str(loss),
                 blocked=state["blocked"] or loss >= Decimal(str(run.policy["max_daily_loss_pct"])))
    run.risk_state = state
    return "Daily loss limit reached; new entries paused until the next trading day. Exits remain active." if state["blocked"] else None


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
                   *, automatic_execution: bool = True, entry_check=None) -> list[str]:
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
            blockers.append(f"{order.ticker}: {error} Holding last available mark; exit awaits valid data. New buys are paused until all holdings have valid quotes.")
        elif not session_error and (order.mark_as_of is None or utc(quote.as_of) >= utc(order.mark_as_of)):
            order.mark_price = quote.price
            order.mark_as_of = quote.as_of
    drawdown = _update_drawdown(run, orders)
    # Manual mode still marks and tracks drawdown, but must not latch a halt
    # that blocks resume while also refusing to sell.
    if (
        automatic_execution
        and drawdown >= Decimal(str(policy["max_drawdown_pct"]))
        and not run.halt_reason
    ):
        run.halt_reason = (
            f"{policy['max_drawdown_pct']}% peak-to-trough drawdown limit "
            "reached; automatic liquidation."
        )
        run.status = "halted"
        _cancel_pending(orders, run.halt_reason)
    elif (
        not automatic_execution
        and not run.halt_reason
        and drawdown >= Decimal(str(policy["max_drawdown_pct"]))
    ):
        blockers.append(
            f"Drawdown is {drawdown.quantize(Decimal('0.01'))}% against the "
            f"{policy['max_drawdown_pct']}% policy. Automatic mode would halt "
            "and liquidate."
        )
    for order in orders:
        if order.status != "open" or session_error or _short(order):
            continue
        # Forced risk exits complete even in Manual so a latched halt cannot
        # strand open positions. Discretionary stops/targets stay Automatic-only.
        forced_exit = run.status in {"liquidating", "halted"}
        if not automatic_execution and not forced_exit:
            continue
        quote = quotes.get(order.instrument_id)
        if _position_quote_rejection(order, quote, now) or utc(quote.as_of) <= utc(order.entry_quote_at):
            continue
        reason = None
        if forced_exit:
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
        if reason == "take_profit" and _scale_long(run, order, max(CENT, price), now):
            continue
        order.exit_price = max(CENT, price)
        order.exit_fee = fee(order.exit_price * order.quantity, policy)
        run.cash_balance = money(run.cash_balance + order.exit_price * order.quantity - order.exit_fee)
        order.realized_pnl = money(order.realized_pnl + (order.exit_price - order.entry_price) * order.quantity - order.entry_fee - order.exit_fee)
        order.status = "closed"
        order.closed_at = now
        order.exit_quote_at = quote.as_of
        order.exit_reason = reason
    # Any unreliable open mark stops new risk, but never disables exit processing.
    daily_block = daily_loss_blocker(run, orders, now)
    if daily_block:
        blockers.append(daily_block)
        _cancel_pending(orders, daily_block)
    uncertain_marks = getattr(run, "_external_marks_unreliable", False) or any(_position_quote_rejection(o, quotes.get(o.instrument_id), now) for o in orders if o.status == "open")
    for order in orders:
        if _short(order) or order.status != "pending" or run.status != "running" or session_error or uncertain_marks or not automatic_execution:
            continue
        if daily_loss_blocker(run, orders, now):
            _cancel_pending(orders, "Daily loss limit reached; entry cancelled.")
            break
        if _update_drawdown(run, orders) >= Decimal(str(policy["max_drawdown_pct"])):
            run.halt_reason = f"{policy['max_drawdown_pct']}% drawdown limit reached during execution; automatic liquidation."
            run.status = "halted"
            _cancel_pending(orders, run.halt_reason)
            break
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
                           if o is not order and not _short(o) and o.status in {"pending", "open"} and o.sector == order.sector), ZERO)
        stop_fill = (order.stop_price * (1 - Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
        planned_loss = (price - stop_fill) * order.quantity + fee(price * order.quantity, policy) + fee(stop_fill * order.quantity, policy)
        active = [o for o in orders if o.status in {"pending", "open"} and not _short(o)] + getattr(run, "_external_holdings", [])
        count = len({getattr(o, "instrument_id", id(o)) for o in active})
        position_used = sum(((o.mark_price or o.limit_price) * o.quantity for o in active
                             if o is not order and getattr(o, "instrument_id", None) == order.instrument_id), ZERO)
        asset_class = (getattr(order, "evidence", None) or {}).get("asset_class", "equity")
        if (count > policy["max_positions"] or cost > run.cash_balance - other_reserved - reserve_floor
                or cost + position_used > state["equity"] * Decimal(str(position_cap(policy, asset_class))) / 100
                or cost + sector_used > state["equity"] * Decimal(str(policy["max_sector_pct"])) / 100
                or planned_loss > state["equity"] * Decimal(str(policy["risk_per_trade_pct"])) / 100
                or ("max_aggregate_risk_pct" in policy and aggregate_risk(run, orders) > state["equity"] * Decimal(str(policy["max_aggregate_risk_pct"])) / 100)):
            order.status = "cancelled"
            order.exit_reason = "Capital or concentration limit changed before fill."
            continue
        if entry_check is not None:
            decision = entry_check(order)
            order.evidence = {**(order.evidence or {}), "fill_risk": decision}
            if not decision["approved"]:
                order.status = "cancelled"
                order.exit_reason = ("Risk: " + "; ".join(decision["reasons"]))[:255]
                blockers.append(f"{order.ticker}: {order.exit_reason}")
                continue
        order.entry_price = price
        order.entry_fee = fee(price * order.quantity, policy)
        run.cash_balance = money(run.cash_balance - cost)
        order.evidence = {**(order.evidence or {}), "opened_quantity": order.quantity}
        order.status = "open"
        order.opened_at = now
        order.entry_quote_at = quote.as_of
        order.mark_price = quote.price
        order.mark_as_of = quote.as_of
    if (
        automatic_execution
        and _update_drawdown(run, orders) >= Decimal(str(policy["max_drawdown_pct"]))
        and not run.halt_reason
    ):
        run.halt_reason = (
            f"{policy['max_drawdown_pct']}% drawdown limit reached after "
            "execution costs; automatic liquidation."
        )
        run.status = "halted"
        _cancel_pending(orders, run.halt_reason)
    elif not automatic_execution:
        _update_drawdown(run, orders)
    after_daily = daily_loss_blocker(run, orders, now)
    if after_daily:
        _cancel_pending(orders, after_daily)
        blockers.append(after_daily)
    from app.services.paper_fund.hedge import process_shorts
    blockers.extend(process_shorts(run, orders, quotes, now, automatic=automatic_execution, session_error=session_error))
    if run.status in {"liquidating", "halted"} and not any(o.status == "open" for o in orders):
        if getattr(run, "_external_holdings", []):
            blockers.append("Automatic positions are closed; manually managed holdings remain in Capital and require separate management.")
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


async def cycle(session: AsyncSession, owner: str, *, now: datetime | None = None,
                include_overview: bool = True) -> PaperFundResponse | None:
    import asyncio
    from sqlalchemy import text
    try:
        async with asyncio.timeout(CYCLE_TIMEOUT_SECONDS):
            # Bound lock waits and abandoned pooler transactions as well as
            # client-side work. An interrupted cycle must release its cash lock.
            await session.execute(text("SELECT set_config('lock_timeout', '5s', true), "
                                       "set_config('idle_in_transaction_session_timeout', '60s', true)"))
            return await _cycle(session, owner, now=now, include_overview=include_overview)
    except BaseException:
        await session.rollback()
        raise


CYCLE_TIMEOUT_SECONDS = 60


async def _cycle(session: AsyncSession, owner: str, *, now: datetime | None = None,
                 include_overview: bool = True) -> PaperFundResponse | None:
    # All Capital mutations use this same lock before touching execution state.
    portfolio = await _portfolio(session, owner)
    run = await _latest(session, owner, lock=True)
    now = utc(now or datetime.now(timezone.utc))
    if run is None:
        raise PaperFundError("Enable automatic trading first.")
    if run.portfolio_id is None:
        raise PaperFundError("Existing execution history must be attached to Capital before trading.")
    if run.status == "completed" or (run.last_cycle_at is not None and now < utc(run.last_cycle_at)):
        return await overview(session, owner, now=now) if include_overview else None
    orders = await _orders(session, run)
    run.policy = await capital_policy(session, portfolio.id, profile=portfolio.risk_profile)
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
    from types import SimpleNamespace
    from app.services.risk.risk_centre import _load_price_histories
    from app.services.paper_fund.risk import entry_risk
    instruments, histories = {}, {}
    if automatic and run.status == "running" and now < utc(run.ends_at) and not market_blocker(now):
        latest_radar = select(RadarRun.id).where(RadarRun.status == "completed", RadarRun.started_at <= now).order_by(RadarRun.started_at.desc(), RadarRun.created_at.desc(), RadarRun.id.desc()).limit(1).scalar_subquery()
        candidates = select(RadarSnapshot.ticker).where(RadarSnapshot.run_id == latest_radar, RadarSnapshot.radar_priority.in_(["P0", "P1"]))
        instruments = {i.id: i for i in await session.scalars(select(Instrument).where(
            (Instrument.id.in_(instrument_ids)) | (Instrument.ticker.in_(candidates))))}
        histories = await _load_price_histories(session, [SimpleNamespace(ticker=i.ticker) for i in instruments.values()], as_of=now.date())
    for order in orders:
        if order.instrument_id in instruments:
            order.evidence = {**(order.evidence or {}), "asset_class": instruments[order.instrument_id].asset_class}
    def entry_check(order):
        identity_error = instrument_rejection(instruments.get(order.instrument_id), now)
        if identity_error:
            return {"approved": False, "reasons": [identity_error]}
        try:
            return entry_risk(run, orders, order, instruments, histories, now)
        except (ArithmeticError, ValueError, TypeError):
            return {"approved": False, "reasons": ["Invalid risk observations; entry blocked pending fresh data."]}
    signal_ids = {o.signal_id for o in orders if o.status == "pending" and o.signal_id}
    pending_signals = {s.id: s for s in await session.scalars(select(RadarSnapshot).where(
        RadarSnapshot.id.in_(signal_ids)))} if signal_ids else {}
    def fill_check(order):
        signal = pending_signals.get(order.signal_id)
        error = (execution_rejection(signal, quotes.get(order.instrument_id), now) if signal
                 else "The original radar signal is unavailable; entry must be rescreened.")
        if error:
            return {"approved": False, "reasons": [error]}
        return entry_check(order)
    before = {o.id: o.status for o in orders}
    if not automatic:
        _cancel_pending(orders, "Manual mode; automatic entry cancelled.")
    blockers = process_orders(run, orders, quotes, now, automatic_execution=automatic, entry_check=fill_check)
    blockers.extend(external_errors)
    if not automatic:
        blockers.insert(0, "Manual mode: ordinary entries and exits are paused; already-triggered liquidation continues.")
    await book_fills(session, portfolio, orders)
    from app.services.paper_fund.hedge import charge_borrow
    await charge_borrow(session, portfolio, orders, now)
    # The engine's validated marks update the shared position book as well.
    for position in await session.scalars(select(Position).where(Position.portfolio_id == portfolio.id, Position.quantity > 0)):
        quote = quotes.get(position.instrument_id)
        if not market_blocker(now) and not quote_rejection(quote, now):
            position.market_value = money(position.quantity * quote.price)
            if (getattr(position, "exposure_side", None) or "long") == "short":
                position.unrealized_pnl = money((position.average_cost - quote.price) * position.quantity)
            else:
                position.unrealized_pnl = money((quote.price - position.average_cost) * position.quantity)
    await session.flush()
    book = await load_book(session, portfolio)
    bind_book(run, orders, book)
    decisions = []
    if automatic and run.status == "running" and not market_blocker(now) and not run.halt_reason:
        from app.services.paper_fund.hedge import queue_hedge
        await queue_hedge(session, run, orders, now, blockers)
    if automatic and run.status == "running" and not market_blocker(now) and not external_errors and not daily_loss_blocker(run, orders, now):
        stale_held = any(_position_quote_rejection(o, quotes.get(o.instrument_id), now) for o in orders if o.status == "open")
        if not stale_held:
            await _queue_signals(session, run, orders, now, blockers, entry_check=entry_check, decisions=decisions)
    if run.status == "completed":
        portfolio.trading_mode = "manual"
    run.last_cycle_at = now
    run.blockers = list(dict.fromkeys(blockers))[:30]
    await session.flush()
    transitions = [{"order_id": str(o.id), "ticker": o.ticker, "from": before.get(o.id),
                    "to": o.status, "reason": o.exit_reason,
                    "risk": (o.evidence or {}).get("fill_risk")}
                   for o in orders if before.get(o.id) != o.status]
    session.add(PaperCycleEvent(run_id=run.id, recorded_at=now, decisions=decisions,
                               transitions=transitions, blockers=list(dict.fromkeys(blockers))))
    await _snapshot(session, run, orders, now, book=book,
                    force=bool(transitions) or run.status == "completed")
    await session.commit()
    return await overview(session, owner, now=now) if include_overview else None


async def _queue_signals(session: AsyncSession, run: PaperFundRun, orders: list[PaperOrder], now: datetime, blockers: list[str], *, entry_check=None, decisions=None) -> None:
    decisions = decisions if decisions is not None else []
    def reject(snapshot, code, reason):
        decisions.append({"ticker": snapshot.ticker, "signal_id": str(snapshot.id), "outcome": "blocked", "code": code, "reason": reason})
        if len(blockers) < 30:
            blockers.append(f"{snapshot.ticker}: {reason}")
    radar_run = await session.scalar(select(RadarRun).where(RadarRun.status == "completed", RadarRun.started_at <= now)
                                      .order_by(RadarRun.started_at.desc(), RadarRun.created_at.desc(), RadarRun.id.desc()).limit(1))
    if radar_run is None:
        blockers.append("Waiting for a completed market radar scan.")
        return
    rows = list((await session.execute(select(RadarSnapshot, Instrument, InstrumentQuote)
        .outerjoin(Instrument, Instrument.ticker == RadarSnapshot.ticker)
        .outerjoin(InstrumentQuote, InstrumentQuote.instrument_id == Instrument.id)
        .where(RadarSnapshot.run_id == radar_run.id)
        .where(RadarSnapshot.radar_priority.in_(["P0", "P1"]))
        .order_by(RadarSnapshot.priority_score.desc(), RadarSnapshot.ticker))).all())
    external = {p.instrument_id for p in getattr(run, "_external_holdings", [])}
    added = 0
    for snapshot, instrument, quote in rows:
        if instrument is None:
            reject(snapshot, "instrument_missing", "No verified instrument and executable quote have been loaded from the data provider.")
            continue
        if instrument.id in external:
            reject(snapshot, "manual_holding", "This instrument is already held under manual management.")
            continue
        error = reentry_rejection(run, orders, instrument.id, snapshot, now, accounting(run, orders)["equity"])
        if error:
            reject(snapshot, "attempt_policy", error)
            continue
        error = instrument_rejection(instrument, now) or execution_rejection(snapshot, quote, now)
        if instrument.currency != "USD" or instrument.asset_class not in {"equity", "etf"}:
            error = "Instrument metadata does not match the USD equity mandate."
        if error:
            reject(snapshot, "eligibility", error)
            continue
        quantity, limit, stop, target = size_order(run, orders, quote.price, instrument.sector, instrument.asset_class)
        if quantity <= 0:
            reject(snapshot, "capacity", "No capacity under cash, sector, position or risk limits.")
            continue
        from app.services.paper_fund.calendar import NEW_YORK
        day = now.astimezone(NEW_YORK).date()
        turnover = sum((o.quantity * o.entry_price for o in orders if o.instrument_id == instrument.id
                        and o.opened_at and o.opened_at.astimezone(NEW_YORK).date() == day), ZERO)
        if turnover + quantity * limit > accounting(run, orders)["equity"] * Decimal(str(run.policy["max_symbol_daily_turnover_pct"])) / 100:
            reject(snapshot, "turnover", "Daily entry turnover limit reached for this instrument.")
            continue
        order = PaperOrder(
            run_id=run.id, instrument_id=instrument.id, signal_id=snapshot.id, ticker=instrument.ticker, name=instrument.name,
            sector=instrument.sector, status="pending", quantity=quantity,
            limit_price=limit, stop_price=stop, target_price=target,
            entry_fee=ZERO, exit_fee=ZERO, realized_pnl=ZERO,
            submitted_at=now, expires_at=min(now + timedelta(minutes=run.policy["order_ttl_minutes"]),
                                            utc(snapshot.as_of) + timedelta(seconds=MAX_SIGNAL_AGE_SECONDS),
                                            utc(snapshot.source_as_of) + timedelta(seconds=MAX_SIGNAL_AGE_SECONDS),
                                            utc(run.ends_at)),
            thesis=f"Confirmed positive radar momentum ({snapshot.change_pct}% session move), with measured liquidity and confirmation.",
            evidence={"radar_snapshot_id": str(snapshot.id), "radar_run_id": str(radar_run.id),
                      "quote_as_of": quote.as_of.isoformat(), "quote_source": quote.source,
                      "radar_evidence": snapshot.evidence, "policy_version": run.policy["version"], "asset_class": instrument.asset_class},
        )
        if entry_check is not None:
            decision = entry_check(order)
            if not decision["approved"]:
                reject(snapshot, "risk", "; ".join(decision["reasons"]))
                continue
            order.evidence = {**order.evidence, "queue_risk": decision}
        session.add(order)
        orders.append(order)
        decisions.append({"ticker": snapshot.ticker, "signal_id": str(snapshot.id), "outcome": "queued", "code": "approved", "reason": "Entry checks passed."})
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
                                 policy=await capital_policy(session, portfolio.id, profile=portfolio.risk_profile), simulation_notice=SIMULATION_NOTICE)
    orders = await _orders(session, run)
    book = await load_book(session, portfolio, dashboard_state=dashboard_state)
    reserved = money(sum((reservation(o, run.policy) for o in orders if o.status == "pending"), ZERO)
                     + sum((cover_reserve(o, run.policy) for o in orders), ZERO))
    state = {**book.state, "reserved_cash": reserved, "available_cash": money(book.cash - reserved)}
    history = list(await session.scalars(select(PaperEquitySnapshot).where(PaperEquitySnapshot.run_id == run.id)
                                        .order_by(PaperEquitySnapshot.recorded_at)))
    from app.services.paper_fund.health import worker_health
    from app.services.paper_fund.reporting import review_diagnostics
    diagnostics = review_diagnostics(run, book, history, now)
    diagnostics['workers'] = await worker_health(session, now)
    last_event = await session.scalar(select(PaperCycleEvent).where(PaperCycleEvent.run_id == run.id)
                                     .order_by(PaperCycleEvent.recorded_at.desc(), PaperCycleEvent.id.desc()).limit(1))
    diagnostics['last_decisions'] = last_event.decisions if last_event else []
    diagnostics['decisions_at'] = last_event.recorded_at if last_event else None
    diagnostics['profile_stock_cap_pct'] = profile_policy(portfolio.risk_profile)['max_position_pct']
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
            direction=getattr(o, "direction", None) or "long",
            quantity=o.quantity, limit_price=o.limit_price, stop_price=o.stop_price, target_price=o.target_price,
            entry_price=o.entry_price, exit_price=o.exit_price, mark_price=o.mark_price,
            realized_pnl=o.realized_pnl, fees_paid=o.entry_fee + o.exit_fee,
            created_at=o.submitted_at, expires_at=o.expires_at, opened_at=o.opened_at,
            closed_at=o.closed_at, exit_reason=o.exit_reason, thesis=o.thesis) for o in orders],
        equity_history=[PaperEquityResponse.model_validate(s) for s in history],
        blockers=list(dict.fromkeys(blockers)), policy=run.policy, simulation_notice=SIMULATION_NOTICE,
        diagnostics=diagnostics,
    )
