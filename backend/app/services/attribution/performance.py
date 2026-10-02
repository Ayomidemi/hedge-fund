import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.attribution import (
    AttributionBucketResponse,
    AttributionRealizedEventResponse,
    AttributionReportResponse,
    AttributionRowResponse,
    AttributionSummaryResponse,
)
from app.api.schemas.operating_core import InstrumentResponse
from app.core.auth import AuthenticatedUser
from app.models import CashLedgerEntry, Instrument, MarketPriceBar, Position, Trade
from app.services.market_data.fx_convert import amount_in_base
from app.services.portfolio.calculations import (
    PositionSnapshot,
    calculate_nav,
    money,
    percent,
)
from app.services.portfolio.operating_core import (
    CapitalValidationError,
    _ensure_fx_rates,
    _trade_fees_in_base,
    _trade_price_in_base,
    cash_balance_in_base,
    get_or_create_default_portfolio,
)

logger = logging.getLogger(__name__)

PERCENT_QUANT = Decimal("0.01")
RATIO_QUANT = Decimal("0.01")
FILLED_STATUS = "filled"
TRADE_ENTRY_TYPES = {"trade_buy", "trade_sell"}


@dataclass
class InstrumentAccumulator:
    instrument: Instrument
    remaining_quantity: Decimal = Decimal("0")
    remaining_cost: Decimal = Decimal("0")
    remaining_entry_fees: Decimal = Decimal("0")
    gross_buys: Decimal = Decimal("0")
    gross_sells: Decimal = Decimal("0")
    gross_realized_pnl: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    trade_count: int = 0
    closed_trade_count: int = 0
    winning_trade_count: int = 0
    losing_trade_count: int = 0
    realized_profit: Decimal = Decimal("0")
    realized_loss: Decimal = Decimal("0")


@dataclass
class BucketAccumulator:
    market_value: Decimal = Decimal("0")
    gross_traded_value: Decimal = Decimal("0")
    gross_realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")
    tickers: set[str] = field(default_factory=set)


async def build_attribution_report(
    session: AsyncSession,
    user: AuthenticatedUser,
    period_start: date | None = None,
    period_end: date | None = None,
) -> AttributionReportResponse:
    if period_start is not None and period_end is not None and period_start >= period_end:
        raise CapitalValidationError("The reporting period must end after it starts.")
    portfolio = await get_or_create_default_portfolio(session, user)
    cash_entries = await _list_cash_entries(
        session,
        portfolio.id,
        period_end=period_end,
    )
    positions = await _list_positions(session, portfolio.id)
    all_trades = await _list_trades(
        session,
        portfolio.id,
    )
    trades = [
        trade for trade in all_trades
        if period_end is None or trade.trade_date.date() < period_end
    ]

    fx_rates = await _ensure_fx_rates(
        session, portfolio=portfolio, instruments=[trade.instrument for trade in trades]
    )
    cash_balance = await cash_balance_in_base(session, portfolio, cash_entries)
    normalized_cash = []
    for entry in cash_entries:
        if entry.entry_date > date.today():
            continue
        if entry.currency != portfolio.base_currency:
            raise CapitalValidationError(
                "Historical performance of foreign-currency cash requires booked FX flows; current FX cannot reconstruct past returns."
            )
        amount = amount_in_base(entry.amount, entry.currency, portfolio.base_currency, fx_rates)
        if amount is None:
            raise CapitalValidationError(f"Cannot convert {entry.currency} cash for attribution.")
        normalized_cash.append(SimpleNamespace(
            entry_date=entry.entry_date, entry_type=entry.entry_type, amount=amount
        ))
    opening_positions = {}
    opening_nav = Decimal("0")
    accumulators, realized_events, warnings = _accumulate_trade_attribution(
        trades, period_start=period_start, portfolio=portfolio, fx_rates=fx_rates
    )
    if period_start is not None or period_end is not None:
        tracked_ids = {trade.instrument_id for trade in all_trades if trade.status == FILLED_STATUS}
        if any(position.quantity > 0 and position.instrument_id not in tracked_ids for position in positions):
            raise CapitalValidationError(
                "Historical attribution requires trade history for every imported position."
            )
    if period_end is not None and period_end <= date.today():
        positions = await _historical_positions(session, accumulators, period_end, portfolio)
    if period_start is not None:
        opening_accumulators, _, _ = _accumulate_trade_attribution(
            [trade for trade in trades if trade.trade_date.date() < period_start],
            portfolio=portfolio, fx_rates=fx_rates,
        )
        opening_positions = {
            position.instrument_id: position
            for position in await _historical_positions(
                session, opening_accumulators, period_start, portfolio
            )
        }
        opening_nav = money(
            sum((entry.amount for entry in normalized_cash if entry.entry_date < period_start), Decimal("0"))
            + sum((position.market_value for position in opening_positions.values()), Decimal("0"))
        )
    period_cash = [
        entry for entry in normalized_cash
        if period_start is None or entry.entry_date >= period_start
    ]
    invested_value = money(
        sum(
            (
                position.market_value
                for position in positions
                if position.quantity > 0
            ),
            Decimal("0"),
        )
    )
    nav = calculate_nav(
        cash_balance,
        [
            PositionSnapshot(
                ticker=position.instrument.ticker,
                asset_class=position.instrument.asset_class,
                sector=position.instrument.sector,
                market_value=position.market_value,
            )
            for position in positions
            if position.quantity > 0
        ],
    )

    for position in positions:
        accumulators.setdefault(
            position.instrument_id,
            InstrumentAccumulator(instrument=position.instrument),
        )

    position_by_instrument_id = {
        position.instrument_id: position for position in positions
    }
    rows = _build_rows(
        accumulators, position_by_instrument_id, nav,
        opening_positions=opening_positions,
    )
    asset_buckets = _build_buckets(rows, nav, key="asset_class")
    sector_buckets = _build_buckets(rows, nav, key="sector")

    total_fees = money(sum((row.fees for row in rows), Decimal("0")))
    gross_realized_pnl = money(
        sum((row.gross_realized_pnl for row in rows), Decimal("0"))
    )
    unrealized_pnl = money(sum((row.unrealized_pnl for row in rows), Decimal("0")))
    net_pnl = money(gross_realized_pnl + unrealized_pnl - total_fees)
    external_entries = [_external_cash_entry(entry) for entry in period_cash]
    net_external_flow = money(sum(external_entries, Decimal("0")))
    total_deposits = money(
        sum((amount for amount in external_entries if amount > 0), Decimal("0"))
    )
    total_withdrawals = money(
        abs(sum((amount for amount in external_entries if amount < 0), Decimal("0")))
    )
    capital_base = max(
        opening_nav + total_deposits if period_start is not None else total_deposits,
        Decimal("1"),
    )
    portfolio_pnl_from_nav = money(nav - opening_nav - net_external_flow)
    reconciliation_gap = money(net_pnl - portfolio_pnl_from_nav)
    trade_count = sum(row.trade_count for row in rows)
    closed_trade_count = sum(row.closed_trade_count for row in rows)
    winning_trade_count = sum(
        accumulator.winning_trade_count for accumulator in accumulators.values()
    )
    losing_trade_count = sum(
        accumulator.losing_trade_count for accumulator in accumulators.values()
    )
    realized_profit = money(
        sum(
            (accumulator.realized_profit for accumulator in accumulators.values()),
            Decimal("0"),
        )
    )
    realized_loss = money(
        sum(
            (accumulator.realized_loss for accumulator in accumulators.values()),
            Decimal("0"),
        )
    )
    gross_traded_value = money(
        sum((row.gross_buys + row.gross_sells for row in rows), Decimal("0"))
    )

    notes = _build_notes(
        trade_count=trade_count,
        reconciliation_gap=reconciliation_gap,
        warnings=warnings,
        period_scoped=period_start is not None or period_end is not None,
    )
    period_dates = _period_dates(
        cash_entries,
        trades,
        period_start=period_start,
        period_end=period_end,
    )

    logger.info(
        "attribution_report_generated",
        extra={
            "portfolio_id": str(portfolio.id),
            "owner_user_id": portfolio.owner_user_id,
            "nav": str(nav),
            "net_pnl": str(net_pnl),
            "trade_count": trade_count,
            "position_count": len(
                [position for position in positions if position.quantity > 0]
            ),
        },
    )

    return AttributionReportResponse(
        summary=AttributionSummaryResponse(
            portfolio_id=portfolio.id,
            portfolio_name=portfolio.name,
            generated_at=datetime.now(timezone.utc),
            period_start=period_dates[0],
            period_end=period_dates[1],
            nav=nav,
            cash_balance=cash_balance,
            invested_value=invested_value,
            net_external_flow=net_external_flow,
            total_deposits=total_deposits,
            total_withdrawals=total_withdrawals,
            gross_traded_value=gross_traded_value,
            total_fees=total_fees,
            gross_realized_pnl=gross_realized_pnl,
            unrealized_pnl=unrealized_pnl,
            net_pnl=net_pnl,
            portfolio_pnl_from_nav=portfolio_pnl_from_nav,
            reconciliation_gap=reconciliation_gap,
            total_return_pct=percent(net_pnl, capital_base),
            fee_drag_pct=percent(total_fees, max(nav, Decimal("1"))),
            turnover_pct=percent(gross_traded_value, capital_base),
            hit_rate_pct=_hit_rate(winning_trade_count, closed_trade_count),
            profit_factor=_profit_factor(realized_profit, realized_loss),
            trade_count=trade_count,
            closed_trade_count=closed_trade_count,
            winning_trade_count=winning_trade_count,
            losing_trade_count=losing_trade_count,
        ),
        by_ticker=rows,
        by_asset_class=asset_buckets,
        by_sector=sector_buckets,
        realized_events=sorted(
            realized_events,
            key=lambda event: event.trade_date,
            reverse=True,
        )[:25],
        notes=notes,
    )


def _accumulate_trade_attribution(
    trades: list[Trade],
    *,
    period_start: date | None = None,
    portfolio=None,
    fx_rates: dict | None = None,
) -> tuple[
    dict[UUID, InstrumentAccumulator],
    list[AttributionRealizedEventResponse],
    list[str],
]:
    accumulators: dict[UUID, InstrumentAccumulator] = {}
    realized_events: list[AttributionRealizedEventResponse] = []
    warnings: list[str] = []

    for trade in trades:
        in_period = period_start is None or trade.trade_date.date() >= period_start
        if trade.status != FILLED_STATUS or trade.executed_price is None:
            if in_period:
                warnings.append(
                    f"{trade.instrument.ticker} trade {trade.id} skipped because it is not filled."
                )
            continue

        accumulator = accumulators.setdefault(
            trade.instrument_id,
            InstrumentAccumulator(instrument=trade.instrument),
        )
        portfolio = portfolio or SimpleNamespace(base_currency="USD")
        price = _trade_price_in_base(trade, trade.instrument, portfolio, fx_rates or {})
        fees = _trade_fees_in_base(trade, trade.instrument, portfolio, fx_rates or {})
        quantity = trade.quantity
        notional = money(quantity * price)
        if in_period:
            accumulator.trade_count += 1
            accumulator.fees = money(accumulator.fees + fees)

        if trade.side == "buy":
            if in_period:
                accumulator.gross_buys = money(accumulator.gross_buys + notional)
            accumulator.remaining_cost += quantity * price
            accumulator.remaining_quantity += quantity
            accumulator.remaining_entry_fees += fees
            continue

        if in_period:
            accumulator.gross_sells = money(accumulator.gross_sells + notional)
        if accumulator.remaining_quantity <= 0:
            if in_period:
                warnings.append(
                    f"{trade.instrument.ticker} has a sell without an available long position."
                )
            continue

        average_cost = accumulator.remaining_cost / accumulator.remaining_quantity
        attributable_quantity = min(quantity, accumulator.remaining_quantity)
        if attributable_quantity < quantity and in_period:
            warnings.append(
                f"{trade.instrument.ticker} sell exceeds the tracked long quantity."
            )

        allocated_entry_fees = money(
            accumulator.remaining_entry_fees * attributable_quantity / accumulator.remaining_quantity
        )
        gross_realized = money(attributable_quantity * (price - average_cost))
        exit_fees = money(fees + allocated_entry_fees)
        net_realized = money(gross_realized - exit_fees)
        accumulator.remaining_entry_fees -= allocated_entry_fees
        accumulator.remaining_cost -= average_cost * attributable_quantity
        accumulator.remaining_quantity -= attributable_quantity
        if accumulator.remaining_quantity == 0:
            accumulator.remaining_cost = Decimal("0")

        if in_period:
            accumulator.gross_realized_pnl = money(
                accumulator.gross_realized_pnl + gross_realized
            )
            accumulator.closed_trade_count += 1
            if net_realized > 0:
                accumulator.winning_trade_count += 1
                accumulator.realized_profit = money(
                    accumulator.realized_profit + net_realized
                )
            elif net_realized < 0:
                accumulator.losing_trade_count += 1
                accumulator.realized_loss = money(
                    accumulator.realized_loss + abs(net_realized)
                )

            realized_events.append(
                AttributionRealizedEventResponse(
                    trade_id=trade.id,
                    trade_date=trade.trade_date,
                    instrument=InstrumentResponse.model_validate(trade.instrument),
                    quantity=attributable_quantity,
                    exit_price=price,
                    average_cost=_quantize_price(average_cost),
                    gross_realized_pnl=gross_realized,
                    fees=exit_fees,
                    net_realized_pnl=net_realized,
                    return_pct=percent(price - average_cost, average_cost),
                )
            )

    return accumulators, realized_events, warnings


def _build_rows(
    accumulators: dict[UUID, InstrumentAccumulator],
    position_by_instrument_id: dict[UUID, Position],
    nav: Decimal,
    *,
    opening_positions: dict | None = None,
) -> list[AttributionRowResponse]:
    rows: list[AttributionRowResponse] = []

    for instrument_id, accumulator in accumulators.items():
        position = position_by_instrument_id.get(instrument_id)
        quantity = position.quantity if position is not None else Decimal("0")
        average_cost = (
            position.average_cost
            if position is not None
            else _average_remaining_cost(accumulator)
        )
        market_value = (
            position.market_value
            if position is not None and position.quantity > 0
            else Decimal("0")
        )
        unrealized_pnl = (
            position.unrealized_pnl
            if position is not None and position.quantity > 0
            else Decimal("0")
        )
        opening_position = (opening_positions or {}).get(instrument_id)
        if opening_position is not None:
            unrealized_pnl -= opening_position.unrealized_pnl
        net_pnl = money(
            accumulator.gross_realized_pnl + unrealized_pnl - accumulator.fees
        )
        traded_capital = accumulator.gross_buys
        status = "open" if quantity > 0 else "closed"
        if accumulator.trade_count == 0 and quantity > 0:
            status = (
                "carried_forward"
                if accumulator.remaining_quantity > 0
                else "imported"
            )

        rows.append(
            AttributionRowResponse(
                instrument=InstrumentResponse.model_validate(accumulator.instrument),
                status=status,
                quantity=quantity,
                average_cost=_quantize_price(average_cost),
                market_value=money(market_value),
                portfolio_weight_pct=percent(market_value, nav),
                gross_buys=money(accumulator.gross_buys),
                gross_sells=money(accumulator.gross_sells),
                gross_realized_pnl=money(accumulator.gross_realized_pnl),
                unrealized_pnl=money(unrealized_pnl),
                fees=money(accumulator.fees),
                net_pnl=net_pnl,
                contribution_pct_nav=percent(net_pnl, max(nav, Decimal("1"))),
                return_on_traded_capital_pct=percent(net_pnl, traded_capital),
                trade_count=accumulator.trade_count,
                closed_trade_count=accumulator.closed_trade_count,
                win_rate_pct=_hit_rate(
                    accumulator.winning_trade_count,
                    accumulator.closed_trade_count,
                ),
            )
        )

    return sorted(
        rows,
        key=lambda row: (row.net_pnl, row.market_value),
        reverse=True,
    )


def _build_buckets(
    rows: list[AttributionRowResponse],
    nav: Decimal,
    *,
    key: str,
) -> list[AttributionBucketResponse]:
    buckets: dict[str, BucketAccumulator] = {}
    for row in rows:
        if key == "sector":
            name = row.instrument.sector or "Unclassified"
        else:
            name = row.instrument.asset_class

        bucket = buckets.setdefault(name, BucketAccumulator())
        bucket.market_value += row.market_value
        bucket.gross_traded_value += row.gross_buys + row.gross_sells
        bucket.gross_realized_pnl += row.gross_realized_pnl
        bucket.unrealized_pnl += row.unrealized_pnl
        bucket.fees += row.fees
        bucket.net_pnl += row.net_pnl
        bucket.tickers.add(row.instrument.ticker)

    responses = []
    for name, values in buckets.items():
        market_value = money(values.market_value)
        net_pnl = money(values.net_pnl)
        responses.append(
            AttributionBucketResponse(
                name=name,
                exposure_pct=percent(market_value, nav),
                market_value=market_value,
                gross_traded_value=money(values.gross_traded_value),
                gross_realized_pnl=money(values.gross_realized_pnl),
                unrealized_pnl=money(values.unrealized_pnl),
                fees=money(values.fees),
                net_pnl=net_pnl,
                contribution_pct_nav=percent(net_pnl, max(nav, Decimal("1"))),
                instrument_count=len(values.tickers),
            )
        )

    return sorted(responses, key=lambda bucket: bucket.net_pnl, reverse=True)


async def _list_cash_entries(
    session: AsyncSession,
    portfolio_id: UUID,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[CashLedgerEntry]:
    query = select(CashLedgerEntry).where(CashLedgerEntry.portfolio_id == portfolio_id)
    if period_start is not None:
        query = query.where(CashLedgerEntry.entry_date >= period_start)
    if period_end is not None:
        query = query.where(CashLedgerEntry.entry_date < period_end)
    result = await session.scalars(
        query.order_by(CashLedgerEntry.entry_date.asc(), CashLedgerEntry.created_at.asc())
    )
    return list(result)


async def _list_positions(session: AsyncSession, portfolio_id: UUID) -> list[Position]:
    result = await session.scalars(
        select(Position)
        .options(selectinload(Position.instrument))
        .where(Position.portfolio_id == portfolio_id)
        .order_by(Position.market_value.desc())
    )
    return list(result)


async def _historical_positions(
    session: AsyncSession,
    accumulators: dict[UUID, InstrumentAccumulator],
    cutoff: date,
    portfolio,
) -> list:
    """Reconstruct inventory and mark it before the exclusive date boundary."""
    positions = []
    for instrument_id, accumulator in accumulators.items():
        if accumulator.remaining_quantity <= 0:
            continue
        bar = await session.scalar(
            select(MarketPriceBar)
            .where(
                MarketPriceBar.instrument_id == instrument_id,
                MarketPriceBar.bar_date < cutoff,
                MarketPriceBar.bar_date >= cutoff - timedelta(days=7),
            )
            .order_by(MarketPriceBar.bar_date.desc(), MarketPriceBar.created_at.desc())
            .limit(1)
        )
        if bar is None or bar.close_price <= 0:
            raise CapitalValidationError(
                f"Missing historical close for {accumulator.instrument.ticker} before {cutoff}."
            )
        if bar.currency != portfolio.base_currency:
            raise CapitalValidationError(
                "Historical foreign-currency attribution requires historical FX marks."
            )
        market_value = money(accumulator.remaining_quantity * bar.close_price)
        positions.append(SimpleNamespace(
            instrument_id=instrument_id,
            instrument=accumulator.instrument,
            quantity=accumulator.remaining_quantity,
            average_cost=accumulator.remaining_cost / accumulator.remaining_quantity,
            market_value=market_value,
            unrealized_pnl=money(market_value - accumulator.remaining_cost),
        ))
    return positions


async def _list_trades(
    session: AsyncSession,
    portfolio_id: UUID,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[Trade]:
    query = (
        select(Trade)
        .options(selectinload(Trade.instrument))
        .where(Trade.portfolio_id == portfolio_id)
        .where(Trade.trade_date <= datetime.now(timezone.utc))
    )
    if period_start is not None:
        query = query.where(
            Trade.trade_date
            >= datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc)
        )
    if period_end is not None:
        query = query.where(
            Trade.trade_date
            < datetime.combine(period_end, datetime.min.time(), tzinfo=timezone.utc)
        )
    result = await session.scalars(
        query.order_by(Trade.trade_date.asc(), Trade.created_at.asc())
    )
    return list(result)


def _external_cash_entry(entry: CashLedgerEntry) -> Decimal:
    if entry.entry_type in TRADE_ENTRY_TYPES:
        return Decimal("0")
    return entry.amount


def _period_dates(
    cash_entries: list[CashLedgerEntry],
    trades: list[Trade],
    *,
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[date | None, date]:
    if period_start is not None or period_end is not None:
        display_end = (period_end - timedelta(days=1)) if period_end else date.today()
        return (period_start, display_end)
    dates = [entry.entry_date for entry in cash_entries]
    dates.extend(trade.trade_date.date() for trade in trades)
    return (min(dates) if dates else None, date.today())


def _average_remaining_cost(accumulator: InstrumentAccumulator) -> Decimal:
    if accumulator.remaining_quantity <= 0:
        return Decimal("0")
    return accumulator.remaining_cost / accumulator.remaining_quantity


def _hit_rate(winning_count: int, closed_count: int) -> Decimal | None:
    if closed_count <= 0:
        return None
    return ((Decimal(winning_count) / Decimal(closed_count)) * Decimal("100")).quantize(
        PERCENT_QUANT,
        rounding=ROUND_HALF_UP,
    )


def _profit_factor(
    realized_profit: Decimal,
    realized_loss: Decimal,
) -> Decimal | None:
    if realized_loss <= 0:
        return None
    return (realized_profit / realized_loss).quantize(
        RATIO_QUANT,
        rounding=ROUND_HALF_UP,
    )


def _quantize_price(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _build_notes(
    *,
    trade_count: int,
    reconciliation_gap: Decimal,
    warnings: list[str],
    period_scoped: bool = False,
) -> list[str]:
    notes = [
        "Attribution uses filled trade journal entries, current position marks, and cash-ledger external flows.",
        "Gross realized P&L is separated from transaction costs; net P&L deducts all recorded trade fees.",
        "Execution P&L and fees are reported in the portfolio base currency; new fills retain their booked FX conversion.",
        "Hit rate and profit factor include allocated entry fees and exit fees.",
    ]
    if period_scoped:
        notes.append(
            "Period P&L subtracts opening NAV and external flows; unrealized P&L is the change since the opening historical mark. Completed periods use historical closing prices."
        )
    if trade_count == 0:
        notes.append(
            "No filled trades are available yet, so attribution is limited to cash and imported positions."
        )
    if abs(reconciliation_gap) >= Decimal("0.05"):
        notes.append(
            f"Ledger reconciliation gap is {reconciliation_gap}; review manual entries and position marks."
        )
    notes.extend(warnings[:5])
    return notes
