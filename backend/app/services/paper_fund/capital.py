"""Capital is the only cash ledger and position book for automatic fills."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import CashLedgerEntry, Instrument, PaperFundRun, PaperOrder, Position, RiskLimit, Trade
from app.services.attribution.performance import _accumulate_trade_attribution
from app.services.market_data.fx_convert import amount_in_base
from app.services.market_data.fx_refresh import load_fx_rates
from app.services.portfolio.operating_core import (
    CapitalValidationError, _rebuild_positions_from_filled_trades,
    _trade_cash_ledger_values, cash_balance_in_base,
)
from app.services.portfolio.calculations import money

ZERO = Decimal("0")


async def capital_policy(session, portfolio_id, policy):
    """Automation respects the stricter of its own policy and Capital limits."""
    result = dict(policy)
    for limit in await session.scalars(select(RiskLimit).where(
        RiskLimit.portfolio_id == portfolio_id, RiskLimit.is_active.is_(True))):
        if limit.limit_type in {"max_single_equity_position_pct", "max_etf_position_pct"}:
            result["max_position_pct"] = min(result["max_position_pct"], float(limit.threshold_value))
        elif limit.limit_type == "max_sector_exposure_pct":
            result["max_sector_pct"] = min(result["max_sector_pct"], float(limit.threshold_value))
        elif limit.limit_type == "min_cash_allocation_pct":
            result["cash_reserve_pct"] = max(result["cash_reserve_pct"], float(limit.threshold_value))
    return result


@dataclass
class CapitalBook:
    cash: Decimal
    positions: list
    net_contributions: Decimal
    state: dict


async def load_book(session, portfolio) -> CapitalBook:
    positions = list(await session.scalars(select(Position).options(selectinload(Position.instrument))
        .where(Position.portfolio_id == portfolio.id, Position.quantity > 0)
        .execution_options(populate_existing=True)))
    entries = list(await session.scalars(select(CashLedgerEntry).where(CashLedgerEntry.portfolio_id == portfolio.id)))
    cash = await cash_balance_in_base(session, portfolio, entries)
    rates = await load_fx_rates(session)
    net_contributions = ZERO
    for entry in entries:
        if entry.entry_type in {"trade_buy", "trade_sell"} or entry.entry_date > date.today():
            continue
        converted = amount_in_base(entry.amount, entry.currency, portfolio.base_currency, rates)
        if converted is None:
            raise CapitalValidationError("Capital cash cannot be valued without its FX rate.")
        net_contributions += converted
    trades = list(await session.scalars(select(Trade).options(selectinload(Trade.instrument))
        .where(Trade.portfolio_id == portfolio.id, Trade.status == "filled")
        .order_by(Trade.trade_date, Trade.created_at)))
    lots, _, _ = _accumulate_trade_attribution(trades, portfolio=portfolio, fx_rates=rates)
    invested = money(sum((position.market_value for position in positions), ZERO))
    equity = money(cash + invested)
    remaining_cost = sum((lot.remaining_cost for lot in lots.values()), ZERO)
    remaining_fees = sum((lot.remaining_entry_fees for lot in lots.values()), ZERO)
    unrealized = money(invested - remaining_cost - remaining_fees)
    total = money(equity - net_contributions)
    return CapitalBook(cash, positions, money(net_contributions), {
        "equity": equity, "unrealized_pnl": unrealized,
        "realized_pnl": money(total - unrealized), "total_pnl": total,
        "return_pct": ((total / net_contributions * 100).quantize(Decimal("0.0001")) if net_contributions > 0 else ZERO),
        "fees_paid": money(sum((lot.fees for lot in lots.values()), ZERO)),
    })


def bind_book(run, orders, book):
    """Add manual holdings to the engine's sizing context, without double counting."""
    run.cash_balance = book.cash
    baseline = run.net_contributions_at_start if run.net_contributions_at_start is not None else book.net_contributions
    run._net_flow_since_start = book.net_contributions - baseline
    managed = {order.instrument_id: order for order in orders if order.status == "open"}
    external = []
    for position in book.positions:
        order = managed.get(position.instrument_id)
        managed_quantity = Decimal(order.quantity) if order else ZERO
        if managed_quantity > position.quantity:
            raise CapitalValidationError("Automatic exit quantity exceeds the Capital position. Reconcile the position first.")
        quantity = position.quantity - managed_quantity
        if quantity > 0:
            external.append(SimpleNamespace(instrument_id=position.instrument_id, sector=position.instrument.sector,
                quantity=quantity, mark_price=position.market_value / position.quantity,
                entry_price=position.average_cost, limit_price=position.average_cost, status="open", entry_fee=ZERO))
    run._external_holdings = external


async def book_fills(session, portfolio, orders):
    """Book each observed fill once, in the caller's locked transaction."""
    changed = False
    events = []
    for order in orders:
        if order.entry_price is not None:
            events.append((order.opened_at, order, "buy", order.entry_price, order.entry_fee))
        if order.exit_price is not None and order.closed_at is not None:
            events.append((order.closed_at, order, "sell", order.exit_price, order.exit_fee))
    for at, order, side, price, fees in sorted(events, key=lambda event: (event[0], event[2] != "buy")):
        key = f"automatic:{order.id}:{side}"
        if await session.scalar(select(Trade.id).where(Trade.portfolio_id == portfolio.id, Trade.idempotency_key == key)):
            continue
        instrument = await session.get(Instrument, order.instrument_id)
        if instrument.currency != portfolio.base_currency or portfolio.base_currency != "USD":
            raise CapitalValidationError("Automatic execution currently requires USD Capital instruments.")
        trade = Trade(portfolio_id=portfolio.id, instrument_id=order.instrument_id,
            trade_date=at, side=side, status="filled", quantity=order.quantity,
            limit_price=order.limit_price if side == "buy" else None,
            executed_price=price, executed_price_base=price, fees=fees, fees_base=fees,
            rationale=order.thesis if side == "buy" else order.exit_reason or "Automatic exit",
            risk_decision="approve", risk_notes="Automatic execution policy and Capital capacity checks passed.",
            broker_reference="automatic_paper", idempotency_key=key)
        session.add(trade)
        await session.flush()
        values = _trade_cash_ledger_values(trade, instrument, portfolio, {})
        if await cash_balance_in_base(session, portfolio) + values["amount"] < 0:
            raise CapitalValidationError("Automatic fill exceeds the Capital account's cash.")
        session.add(CashLedgerEntry(portfolio_id=portfolio.id, **values))
        await session.flush()
        changed = True
    if changed:
        await _rebuild_positions_from_filled_trades(session, portfolio)
        await session.flush()
    return changed


async def release_manual_management(session, portfolio, instrument_id):
    """A manual trade takes over this instrument's existing automation plan."""
    orders = list(await session.scalars(select(PaperOrder).join(PaperFundRun)
        .where(PaperFundRun.portfolio_id == portfolio.id, PaperOrder.instrument_id == instrument_id,
               PaperOrder.status.in_(["pending", "open"]))))
    for order in orders:
        order.status = "cancelled"
        order.exit_reason = "Automatic plan released after a manual trade; remaining holdings stay in Capital."


async def reserved_capital(session, portfolio_id):
    from app.services.paper_fund.engine import reservation
    rows = (await session.execute(select(PaperOrder, PaperFundRun).join(PaperFundRun)
        .where(PaperFundRun.portfolio_id == portfolio_id, PaperOrder.status == "pending"))).all()
    return money(sum((reservation(order, run.policy) for order, run in rows), ZERO))
