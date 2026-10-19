"""One paper SPY hedge. The radar stays long-only, and no other name can be short."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from sqlalchemy import select

from app.models import CashLedgerEntry, Instrument, InstrumentQuote, PaperOrder
from app.services.paper_fund.calendar import NEW_YORK, order_expiry
from app.services.paper_fund.engine import fee, money, utc

ZERO = Decimal("0")
CENT = Decimal("0.01")


def is_short(order) -> bool:
    return (getattr(order, "direction", None) or "long") == "short"


def hedge_levels(price: Decimal, policy: dict) -> tuple[Decimal, Decimal, Decimal]:
    """Sell limit, stop above it, and target below it."""
    slip = Decimal(str(policy["slippage_bps"])) / 10000
    limit = (price * (1 - slip)).quantize(CENT, rounding=ROUND_FLOOR)
    stop = (limit * (1 + Decimal(str(policy["stop_loss_pct"])) / 100)).quantize(CENT, rounding=ROUND_CEILING)
    target = (limit * (1 - Decimal(str(policy["take_profit_pct"])) / 100)).quantize(CENT, rounding=ROUND_FLOOR)
    return limit, stop, target


def hedge_quantity(long_exposure: Decimal, price: Decimal, policy: dict) -> int:
    if long_exposure <= 0 or price <= 0:
        return 0
    budget = long_exposure * Decimal(str(policy.get("hedge_pct", 20))) / 100
    return max(0, int(budget / price))


def long_exposure(run, orders) -> Decimal:
    total = sum(
        ((order.mark_price or order.entry_price or ZERO) * order.quantity
         for order in orders if order.status == "open" and not is_short(order)),
        ZERO,
    )
    total += sum(
        (holding.mark_price * holding.quantity for holding in getattr(run, "_external_holdings", [])),
        ZERO,
    )
    return money(total)


def process_shorts(run, orders, quotes, now: datetime, *, automatic: bool, session_error: str | None) -> None:
    policy = run.policy
    for order in orders:
        if not is_short(order) or order.status != "open" or session_error:
            continue
        forced = run.status in {"liquidating", "halted"}
        if not automatic and not forced:
            continue
        quote = quotes.get(order.instrument_id)
        if quote is None or utc(quote.as_of) <= utc(order.entry_quote_at or order.submitted_at):
            continue
        reason = None
        if forced:
            reason = "drawdown_halt" if run.halt_reason else "review_period_ended"
        elif quote.price >= order.stop_price:
            reason = "stop_loss"
        elif quote.price <= order.target_price:
            reason = "take_profit"
        if reason is None:
            continue
        price = (quote.price * (1 + Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_CEILING)
        if reason == "take_profit" and price > order.target_price:
            continue
        _cover(run, order, max(CENT, price), quote.as_of, now, reason)
    for order in orders:
        if not is_short(order) or order.status != "pending" or not automatic or run.status != "running" or session_error:
            continue
        quote = quotes.get(order.instrument_id)
        if quote is None or utc(quote.as_of) <= utc(order.submitted_at):
            continue
        if quote.price >= order.stop_price:
            order.status = "cancelled"
            order.exit_reason = "Hedge cancelled: the quote is already through the stop."
            continue
        price = (quote.price * (1 - Decimal(str(policy["slippage_bps"])) / 10000)).quantize(CENT, rounding=ROUND_FLOOR)
        if price < order.limit_price:
            continue
        proceeds = money(price * order.quantity - fee(price * order.quantity, policy))
        run.cash_balance = money(run.cash_balance + proceeds)
        order.entry_price = price
        order.entry_fee = fee(price * order.quantity, policy)
        order.status = "open"
        order.opened_at = now
        order.entry_quote_at = quote.as_of
        order.mark_price = quote.price
        order.mark_as_of = quote.as_of
        order.evidence = {**(order.evidence or {}), "opened_quantity": order.quantity, "locate": "paper"}


def _cover(run, order, price, quoted_at, now, reason) -> None:
    policy = run.policy
    cover_fee = fee(price * order.quantity, policy)
    cost = money(price * order.quantity + cover_fee)
    run.cash_balance = money(run.cash_balance - cost)
    entry = order.entry_price or order.limit_price
    order.exit_price = price
    order.exit_fee = cover_fee
    order.realized_pnl = money(order.realized_pnl + (entry - price) * order.quantity - order.entry_fee - cover_fee)
    order.status = "closed"
    order.closed_at = now
    order.exit_quote_at = quoted_at
    order.exit_reason = reason


async def charge_borrow(session, portfolio, orders, now: datetime) -> None:
    day = utc(now).astimezone(NEW_YORK).date().isoformat()
    for order in orders:
        if not is_short(order) or order.status != "open":
            continue
        evidence = dict(order.evidence or {})
        if evidence.get("borrow_on") == day:
            continue
        mark = order.mark_price or order.entry_price or order.limit_price
        bps = Decimal(str((order.evidence or {}).get("borrow_bps_per_day") or 1))
        amount = money(mark * order.quantity * bps / 10000)
        if amount <= 0:
            continue
        key = f"borrow:{order.id}:{day}"
        if await session.scalar(select(CashLedgerEntry.id).where(
            CashLedgerEntry.portfolio_id == portfolio.id, CashLedgerEntry.idempotency_key == key
        )):
            evidence["borrow_on"] = day
            order.evidence = evidence
            continue
        session.add(CashLedgerEntry(
            portfolio_id=portfolio.id, entry_date=utc(now).date(), amount=-amount,
            currency=portfolio.base_currency, entry_type="borrow_fee", platform="automatic_paper",
            description=f"Paper borrow fee for short {order.ticker}.", idempotency_key=key,
        ))
        evidence["borrow_on"] = day
        evidence["borrow_bps_per_day"] = str(bps)
        order.evidence = evidence


async def queue_hedge(session, run, orders, now: datetime, blockers: list[str]) -> None:
    if any(is_short(order) and order.status in {"pending", "open"} for order in orders):
        return
    ticker = str(run.policy.get("hedge_ticker") or "SPY")
    instrument = await session.scalar(select(Instrument).where(Instrument.ticker == ticker))
    if instrument is None or instrument.currency != "USD" or instrument.asset_class not in {"equity", "etf"}:
        blockers.append(f"{ticker}: hedge instrument is not a verified USD listing.")
        return
    if any(order.instrument_id == instrument.id and order.status in {"pending", "open"} for order in orders):
        return
    if any(getattr(holding, "instrument_id", None) == instrument.id for holding in getattr(run, "_external_holdings", [])):
        blockers.append(f"{ticker}: already held long, so it cannot be the hedge.")
        return
    quote = await session.scalar(select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument.id))
    from app.services.market_radar.execution import quote_rejection
    error = quote_rejection(quote, now)
    if error:
        blockers.append(f"{ticker}: {error}")
        return
    expiry = order_expiry(now)
    if expiry is None or expiry <= now:
        return
    quantity = hedge_quantity(long_exposure(run, orders), quote.price, run.policy)
    if quantity <= 0:
        return
    limit, stop, target = hedge_levels(quote.price, run.policy)
    if not ZERO < target < limit < stop:
        return
    order = PaperOrder(
        run_id=run.id, instrument_id=instrument.id, ticker=instrument.ticker, name=instrument.name,
        sector=instrument.sector, direction="short", status="pending", quantity=quantity,
        limit_price=limit, stop_price=stop, target_price=target,
        entry_fee=ZERO, exit_fee=ZERO, realized_pnl=ZERO,
        submitted_at=now, expires_at=expiry,
        thesis=f"Paper hedge: short {ticker} for {run.policy.get('hedge_pct', 20)}% of long exposure.",
        evidence={"hedge": True, "locate": "paper", "borrow_bps_per_day": str(run.policy.get("borrow_bps_per_day", 1))},
    )
    session.add(order)
    orders.append(order)
