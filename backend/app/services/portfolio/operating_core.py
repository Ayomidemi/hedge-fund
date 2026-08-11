import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import AuthenticatedUser
from app.api.schemas.operating_core import (
    CashAdjustmentCreate,
    CashDepositCreate,
    CashLedgerEntryCreate,
    CashLedgerEntryResponse,
    CashMovementCreate,
    CashWithdrawalCreate,
    ExposureBucketResponse,
    InstrumentCreate,
    InstrumentResponse,
    ManualTradeCreate,
    ManualTradeUpdate,
    PortfolioDashboardResponse,
    PortfolioResponse,
    PositionResponse,
    RiskCheckResponse,
    RiskLimitResponse,
    TradeJournalEntryResponse,
    TradeJournalResponse,
    TradeJournalSummaryResponse,
    TradeResponse,
)
from app.models import (
    CashLedgerEntry,
    Instrument,
    InstrumentQuote,
    Portfolio,
    Position,
    RiskLimit,
    Trade,
    TradeSide,
    TradeStatus,
)
from app.services.administration.system_log import record_system_log
from app.services.market_data.fx_convert import price_in_portfolio_base
from app.services.market_data.fx_refresh import load_fx_rates, refresh_fx_rates
from app.services.market_data.quote_cache import get_mark_price, get_mark_prices
from app.services.portfolio.calculations import (
    DEFAULT_RISK_LIMITS,
    PositionSnapshot,
    RiskLimitSnapshot,
    calculate_nav,
    evaluate_risk_limits,
    group_exposure_by_asset_class,
    group_exposure_by_sector,
    money,
)

DEFAULT_PORTFOLIO_NAME = "Operating Fund"
DEFAULT_INITIAL_CAPITAL = Decimal("1000.00")

logger = logging.getLogger(__name__)


class TradeNotFoundError(RuntimeError):
    pass


async def get_dashboard(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> PortfolioDashboardResponse:
    portfolio = await get_or_create_default_portfolio(session, user)

    cash_entries = await _list_cash_entries(session, portfolio.id)
    positions = await _list_positions(session, portfolio.id)
    trades = await _list_trades(session, portfolio.id)
    risk_limits = await _list_risk_limits(session, portfolio.id)

    cash_balance = money(sum((entry.amount for entry in cash_entries), Decimal("0")))
    position_snapshots = [
        PositionSnapshot(
            ticker=position.instrument.ticker,
            asset_class=position.instrument.asset_class,
            sector=position.instrument.sector,
            market_value=position.market_value,
        )
        for position in positions
        if position.quantity > 0
    ]
    nav = calculate_nav(cash_balance, position_snapshots)
    invested_value = money(
        sum(
            (position.market_value for position in positions if position.quantity > 0),
            Decimal("0"),
        )
    )
    risk_checks = evaluate_risk_limits(
        cash_balance=cash_balance,
        positions=position_snapshots,
        nav=nav,
        risk_limits=[_risk_limit_snapshot(limit) for limit in risk_limits],
    )
    breached_checks = [check.limit_type for check in risk_checks if not check.passed]

    logger.info(
        "portfolio_dashboard_loaded",
        extra={
            "portfolio_id": str(portfolio.id),
            "owner_user_id": portfolio.owner_user_id,
            "nav": str(nav),
            "cash_balance": str(cash_balance),
            "open_position_count": len(position_snapshots),
            "trade_count": len(trades),
            "risk_breaches": breached_checks,
        },
    )

    return PortfolioDashboardResponse(
        portfolio=PortfolioResponse.model_validate(portfolio),
        prices_as_of=await _latest_price_timestamp(session, positions),
        cash_balance=cash_balance,
        nav=nav,
        invested_value=invested_value,
        open_position_count=len(
            [position for position in positions if position.quantity > 0]
        ),
        trade_count=len(trades),
        positions=[
            _position_response(position)
            for position in positions
            if position.quantity > 0
        ],
        recent_cash_entries=[
            CashLedgerEntryResponse.model_validate(entry) for entry in cash_entries[:10]
        ],
        recent_trades=[_trade_response(trade) for trade in trades[:10]],
        risk_limits=[RiskLimitResponse.model_validate(limit) for limit in risk_limits],
        risk_checks=[
            RiskCheckResponse(
                name=check.name,
                limit_type=check.limit_type,
                observed_value=check.observed_value,
                threshold_value=check.threshold_value,
                unit=check.unit,
                passed=check.passed,
                severity=check.severity,
                message=check.message,
            )
            for check in risk_checks
        ],
        asset_class_exposure=[
            ExposureBucketResponse(name=name, exposure_pct=value)
            for name, value in group_exposure_by_asset_class(
                position_snapshots, nav
            ).items()
        ],
        sector_exposure=[
            ExposureBucketResponse(name=name, exposure_pct=value)
            for name, value in group_exposure_by_sector(position_snapshots, nav).items()
        ],
    )


async def get_or_create_default_portfolio(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> Portfolio:
    portfolio = await _load_owned_portfolio(session, user)
    if portfolio is not None:
        await _ensure_default_risk_limits(session, portfolio)
        await session.commit()
        return portfolio

    try:
        return await _seed_default_portfolio(session, user)
    except IntegrityError as exc:
        await session.rollback()
        if "ix_portfolios_owner_user_id_unique" not in str(exc):
            raise

        portfolio = await _load_owned_portfolio(session, user)
        if portfolio is None:
            raise

        await _ensure_default_risk_limits(session, portfolio)
        await session.commit()
        await session.refresh(portfolio)

        logger.info(
            "default_portfolio_seed_race_resolved",
            extra={"portfolio_id": str(portfolio.id), "owner_user_id": user.id},
        )
        return portfolio


async def _load_owned_portfolio(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> Portfolio | None:
    return await session.scalar(
        select(Portfolio).where(Portfolio.owner_user_id == user.id)
    )


async def _seed_default_portfolio(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> Portfolio:
    logger.info(
        "default_portfolio_seed_started",
        extra={"portfolio_name": DEFAULT_PORTFOLIO_NAME, "owner_user_id": user.id},
    )

    initial_capital = _starting_capital_for_user(user)
    portfolio = Portfolio(
        owner_user_id=user.id,
        name=_default_portfolio_name(user),
        base_currency="USD",
        mandate="Technology-driven, multi-strategy fund operating core.",
        initial_capital=initial_capital,
    )
    session.add(portfolio)
    await session.flush()

    session.add(
        CashLedgerEntry(
            portfolio_id=portfolio.id,
            entry_date=date.today(),
            amount=initial_capital,
            currency="USD",
            entry_type="initial_capital",
            platform="manual",
            description="Starting capital from account setup.",
            source_reference="account_seed",
        )
    )
    await _ensure_default_risk_limits(session, portfolio)
    await session.commit()
    await session.refresh(portfolio)

    logger.info(
        "default_portfolio_seeded",
        extra={
            "portfolio_id": str(portfolio.id),
            "owner_user_id": user.id,
            "initial_capital": str(initial_capital),
        },
    )
    return portfolio


def _default_portfolio_name(user: AuthenticatedUser) -> str:
    if user.org_name:
        return f"{user.org_name} Operating Fund"
    if user.full_name:
        return f"{user.full_name} Operating Fund"
    if user.email:
        return f"{user.email} Operating Fund"
    return DEFAULT_PORTFOLIO_NAME


def _starting_capital_for_user(user: AuthenticatedUser) -> Decimal:
    if user.starting_capital is None:
        return DEFAULT_INITIAL_CAPITAL
    return max(user.starting_capital, DEFAULT_INITIAL_CAPITAL).quantize(Decimal("0.01"))


async def create_cash_deposit(
    session: AsyncSession,
    payload: CashDepositCreate | CashLedgerEntryCreate,
    user: AuthenticatedUser,
) -> CashLedgerEntryResponse:
    return await _create_cash_entry(
        session,
        payload,
        user,
        entry_type="deposit",
        amount=payload.amount,
    )


async def create_cash_withdrawal(
    session: AsyncSession,
    payload: CashWithdrawalCreate,
    user: AuthenticatedUser,
) -> CashLedgerEntryResponse:
    return await _create_cash_entry(
        session,
        payload,
        user,
        entry_type="withdrawal",
        amount=-abs(payload.amount),
    )


async def create_cash_adjustment(
    session: AsyncSession,
    payload: CashAdjustmentCreate,
    user: AuthenticatedUser,
) -> CashLedgerEntryResponse:
    return await _create_cash_entry(
        session,
        payload,
        user,
        entry_type="adjustment",
        amount=payload.amount,
    )


async def create_cash_entry(
    session: AsyncSession,
    payload: CashLedgerEntryCreate,
    user: AuthenticatedUser,
) -> CashLedgerEntryResponse:
    return await create_cash_deposit(session, payload, user)


async def _create_cash_entry(
    session: AsyncSession,
    payload: CashMovementCreate,
    user: AuthenticatedUser,
    *,
    entry_type: str,
    amount: Decimal,
) -> CashLedgerEntryResponse:
    portfolio = await get_or_create_default_portfolio(session, user)
    entry = CashLedgerEntry(
        portfolio_id=portfolio.id,
        entry_date=payload.entry_date,
        amount=amount,
        currency=payload.currency,
        entry_type=entry_type,
        platform=payload.platform,
        description=payload.description,
        source_reference=payload.source_reference,
    )
    session.add(entry)
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="portfolio",
        event="cash_entry_created",
        message=f"{entry_type.title()} of {amount} {payload.currency} recorded.",
        context={
            "entry_type": entry_type,
            "amount": str(amount),
            "currency": payload.currency,
        },
    )
    await session.commit()
    await session.refresh(entry)

    logger.info(
        "cash_ledger_entry_created",
        extra={
            "portfolio_id": str(portfolio.id),
            "owner_user_id": portfolio.owner_user_id,
            "entry_id": str(entry.id),
            "entry_type": entry.entry_type,
            "platform": entry.platform,
            "amount": str(entry.amount),
            "currency": entry.currency,
        },
    )
    return CashLedgerEntryResponse.model_validate(entry)


async def list_cash_ledger_history(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> list[CashLedgerEntryResponse]:
    portfolio = await get_or_create_default_portfolio(session, user)
    cash_entries = await _list_cash_entries(session, portfolio.id)

    logger.info(
        "cash_ledger_history_loaded",
        extra={
            "portfolio_id": str(portfolio.id),
            "owner_user_id": portfolio.owner_user_id,
            "entry_count": len(cash_entries),
        },
    )

    return [CashLedgerEntryResponse.model_validate(entry) for entry in cash_entries]


async def get_trade_journal(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    limit: int = 100,
) -> TradeJournalResponse:
    portfolio = await get_or_create_default_portfolio(session, user)
    trades = await _list_trades(session, portfolio.id, limit=limit)
    fx_rates = await _ensure_fx_rates(
        session,
        portfolio=portfolio,
        instruments=[trade.instrument for trade in trades],
    )
    entries = [
        _trade_journal_entry_response(trade, portfolio, fx_rates) for trade in trades
    ]
    summary = _trade_journal_summary(entries)

    logger.info(
        "trade_journal_loaded",
        extra={
            "portfolio_id": str(portfolio.id),
            "owner_user_id": portfolio.owner_user_id,
            "trade_count": len(entries),
            "limit": limit,
        },
    )

    return TradeJournalResponse(
        portfolio=PortfolioResponse.model_validate(portfolio),
        summary=summary,
        trades=entries,
    )


async def upsert_instrument(
    session: AsyncSession,
    payload: InstrumentCreate,
) -> Instrument:
    ticker = payload.ticker.upper()
    instrument = await session.scalar(
        select(Instrument).where(Instrument.ticker == ticker)
    )
    if instrument is None:
        instrument = Instrument(
            ticker=ticker,
            name=payload.name,
            asset_class=payload.asset_class,
            exchange=payload.exchange,
            currency=payload.currency,
            sector=payload.sector,
            industry=payload.industry,
        )
        session.add(instrument)
        await session.flush()
        logger.info(
            "instrument_created",
            extra={
                "instrument_id": str(instrument.id),
                "ticker": instrument.ticker,
                "asset_class": instrument.asset_class,
            },
        )
        return instrument

    logger.info(
        "instrument_updated",
        extra={
            "instrument_id": str(instrument.id),
            "ticker": instrument.ticker,
            "asset_class": payload.asset_class,
        },
    )

    instrument.name = payload.name
    instrument.asset_class = payload.asset_class
    instrument.exchange = payload.exchange
    instrument.currency = payload.currency
    instrument.sector = payload.sector
    instrument.industry = payload.industry
    await session.flush()
    return instrument


async def create_manual_trade(
    session: AsyncSession,
    payload: ManualTradeCreate,
    user: AuthenticatedUser,
) -> TradeResponse:
    portfolio = await get_or_create_default_portfolio(session, user)
    instrument = await upsert_instrument(session, payload.instrument)

    fx_rates = await _ensure_fx_rates(
        session, portfolio=portfolio, instruments=[instrument]
    )

    trade = Trade(
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        recommendation_id=None,
        trade_date=payload.trade_date,
        side=payload.side,
        status=TradeStatus.FILLED.value,
        quantity=payload.quantity,
        limit_price=None,
        executed_price=payload.price,
        fees=payload.fees,
        rationale=payload.rationale or "",
        risk_notes=payload.risk_notes,
        broker_reference=payload.broker_reference,
    )
    session.add(trade)
    await session.flush()

    cash_values = _trade_cash_ledger_values(trade, instrument, portfolio, fx_rates)
    session.add(CashLedgerEntry(portfolio_id=portfolio.id, **cash_values))

    await _rebuild_positions_from_filled_trades(session, portfolio)
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="portfolio",
        event="trade_created",
        message=f"{trade.side.upper()} {trade.quantity} {instrument.ticker} recorded.",
        context={
            "trade_id": str(trade.id),
            "ticker": instrument.ticker,
            "side": trade.side,
        },
    )
    await session.commit()

    trade = await session.scalar(
        select(Trade)
        .options(selectinload(Trade.instrument))
        .where(Trade.id == trade.id)
    )
    if trade is None:
        raise RuntimeError("Trade could not be loaded after commit.")

    logger.info(
        "manual_trade_created",
        extra={
            "portfolio_id": str(portfolio.id),
            "owner_user_id": portfolio.owner_user_id,
            "trade_id": str(trade.id),
            "ticker": instrument.ticker,
            "side": trade.side,
            "quantity": str(trade.quantity),
            "executed_price": str(trade.executed_price),
            "cash_amount": str(cash_values["amount"]),
        },
    )

    return _trade_response(trade)


async def update_manual_trade(
    session: AsyncSession,
    trade_id: UUID,
    payload: ManualTradeUpdate,
    user: AuthenticatedUser,
) -> TradeResponse:
    portfolio = await get_or_create_default_portfolio(session, user)
    trade = await session.scalar(
        select(Trade)
        .options(selectinload(Trade.instrument))
        .where(Trade.id == trade_id, Trade.portfolio_id == portfolio.id)
    )
    if trade is None:
        raise TradeNotFoundError("Trade was not found.")

    old_cash_values = _trade_cash_ledger_values(
        trade,
        trade.instrument,
        portfolio,
        await _ensure_fx_rates(
            session, portfolio=portfolio, instruments=[trade.instrument]
        ),
    )
    instrument = await upsert_instrument(session, payload.instrument)
    fx_rates = await _ensure_fx_rates(
        session, portfolio=portfolio, instruments=[instrument]
    )

    trade.instrument_id = instrument.id
    trade.instrument = instrument
    trade.trade_date = payload.trade_date
    trade.side = payload.side
    trade.quantity = payload.quantity
    trade.executed_price = payload.price
    trade.fees = payload.fees
    trade.rationale = payload.rationale or ""
    trade.risk_notes = payload.risk_notes
    trade.broker_reference = payload.broker_reference
    await session.flush()

    await _sync_trade_cash_entry(session, portfolio, trade, instrument, old_cash_values, fx_rates)
    await _rebuild_positions_from_filled_trades(session, portfolio)
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="portfolio",
        event="trade_updated",
        message=f"{trade.side.upper()} {trade.quantity} {trade.instrument.ticker} updated.",
        context={
            "trade_id": str(trade.id),
            "ticker": trade.instrument.ticker,
            "side": trade.side,
        },
    )
    await session.commit()

    trade = await session.scalar(
        select(Trade)
        .options(selectinload(Trade.instrument))
        .where(Trade.id == trade_id, Trade.portfolio_id == portfolio.id)
    )
    if trade is None:
        raise RuntimeError("Trade could not be loaded after update.")

    logger.info(
        "manual_trade_updated",
        extra={
            "portfolio_id": str(portfolio.id),
            "owner_user_id": portfolio.owner_user_id,
            "trade_id": str(trade.id),
            "ticker": trade.instrument.ticker,
            "side": trade.side,
            "quantity": str(trade.quantity),
            "executed_price": str(trade.executed_price),
        },
    )

    return _trade_response(trade)


async def _apply_trade_to_position(
    session: AsyncSession,
    portfolio: Portfolio,
    instrument: Instrument,
    payload: ManualTradeCreate,
) -> None:
    position = await session.scalar(
        select(Position).where(
            Position.portfolio_id == portfolio.id,
            Position.instrument_id == instrument.id,
            Position.closed_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)

    if position is None:
        position = Position(
            portfolio_id=portfolio.id,
            instrument_id=instrument.id,
            quantity=Decimal("0"),
            average_cost=Decimal("0"),
            market_value=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            opened_at=now,
        )
        session.add(position)
        await session.flush()

    if payload.side == TradeSide.BUY.value:
        previous_cost = position.quantity * position.average_cost
        new_cost = payload.quantity * payload.price
        new_quantity = position.quantity + payload.quantity
        position.average_cost = (previous_cost + new_cost) / new_quantity
        position.quantity = new_quantity
    else:
        position.quantity -= payload.quantity
        if position.quantity <= 0:
            position.quantity = Decimal("0")
            position.closed_at = now

    # Mark from the live quote when one is fresh (NGN → USD via FX guard).
    mark_price = await get_mark_price(
        session, instrument=instrument, portfolio=portfolio
    )
    if mark_price is None:
        mark_price = payload.price
    position.market_value = money(position.quantity * mark_price)
    position.unrealized_pnl = money(
        (mark_price - position.average_cost) * position.quantity
    )

    logger.info(
        "position_updated_from_trade",
        extra={
            "portfolio_id": str(portfolio.id),
            "instrument_id": str(instrument.id),
            "ticker": instrument.ticker,
            "quantity": str(position.quantity),
            "average_cost": str(position.average_cost),
            "market_value": str(position.market_value),
        },
    )


async def _sync_trade_cash_entry(
    session: AsyncSession,
    portfolio: Portfolio,
    trade: Trade,
    instrument: Instrument,
    old_cash_values: dict,
    fx_rates: dict,
) -> None:
    entry = await session.scalar(
        select(CashLedgerEntry).where(
            CashLedgerEntry.portfolio_id == portfolio.id,
            CashLedgerEntry.source_reference == _trade_source_reference(trade.id),
        )
    )
    if entry is None:
        entry = await _find_legacy_trade_cash_entry(
            session,
            portfolio.id,
            old_cash_values,
        )

    new_values = _trade_cash_ledger_values(trade, instrument, portfolio, fx_rates)
    if entry is None:
        session.add(CashLedgerEntry(portfolio_id=portfolio.id, **new_values))
        logger.info(
            "trade_cash_entry_recreated",
            extra={"portfolio_id": str(portfolio.id), "trade_id": str(trade.id)},
        )
        return

    for field_name, value in new_values.items():
        setattr(entry, field_name, value)


async def _find_legacy_trade_cash_entry(
    session: AsyncSession,
    portfolio_id: UUID,
    values: dict,
) -> CashLedgerEntry | None:
    return await session.scalar(
        select(CashLedgerEntry)
        .where(
            CashLedgerEntry.portfolio_id == portfolio_id,
            CashLedgerEntry.entry_date == values["entry_date"],
            CashLedgerEntry.amount == values["amount"],
            CashLedgerEntry.entry_type == values["entry_type"],
            CashLedgerEntry.description == values["description"],
            CashLedgerEntry.source_reference == "manual_trade",
        )
        .order_by(CashLedgerEntry.created_at.desc())
        .limit(1)
    )


async def _rebuild_positions_from_filled_trades(
    session: AsyncSession,
    portfolio: Portfolio,
) -> None:
    trades = list(
        await session.scalars(
            select(Trade)
            .options(selectinload(Trade.instrument))
            .where(
                Trade.portfolio_id == portfolio.id,
                Trade.status == TradeStatus.FILLED.value,
                Trade.executed_price.is_not(None),
            )
            .order_by(Trade.trade_date.asc(), Trade.created_at.asc())
        )
    )
    instrument_ids = {trade.instrument_id for trade in trades}
    if not instrument_ids:
        return

    await session.execute(
        delete(Position).where(
            Position.portfolio_id == portfolio.id,
            Position.instrument_id.in_(instrument_ids),
        )
    )

    fx_rates = await _ensure_fx_rates(
        session,
        portfolio=portfolio,
        instruments=[trade.instrument for trade in trades],
    )

    states: dict[UUID, dict] = {}
    for trade in trades:
        trade_price = _trade_price_in_base(trade, trade.instrument, portfolio, fx_rates)
        state = states.setdefault(
            trade.instrument_id,
            {
                "instrument": trade.instrument,
                "quantity": Decimal("0"),
                "average_cost": Decimal("0"),
                "last_price": trade_price,
                "opened_at": trade.trade_date,
            },
        )
        state["last_price"] = trade_price

        if trade.side == TradeSide.BUY.value:
            previous_cost = state["quantity"] * state["average_cost"]
            new_cost = trade.quantity * trade_price
            new_quantity = state["quantity"] + trade.quantity
            state["average_cost"] = (previous_cost + new_cost) / new_quantity
            state["quantity"] = new_quantity
            continue

        state["quantity"] = max(Decimal("0"), state["quantity"] - trade.quantity)
        if state["quantity"] == 0:
            state["average_cost"] = Decimal("0")

    instruments_by_id = {
        instrument_id: state["instrument"] for instrument_id, state in states.items()
    }
    marks = await get_mark_prices(
        session,
        instrument_ids=set(states),
        portfolio=portfolio,
        instruments_by_id=instruments_by_id,
    )

    for instrument_id, state in states.items():
        if state["quantity"] <= 0:
            continue

        mark_price = marks.get(instrument_id, state["last_price"])
        market_value = money(state["quantity"] * mark_price)
        unrealized_pnl = money(
            (mark_price - state["average_cost"]) * state["quantity"]
        )
        session.add(
            Position(
                portfolio_id=portfolio.id,
                instrument_id=instrument_id,
                quantity=state["quantity"],
                average_cost=state["average_cost"],
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                opened_at=state["opened_at"],
            )
        )

    logger.info(
        "positions_rebuilt_from_trades",
        extra={
            "portfolio_id": str(portfolio.id),
            "instrument_count": len(instrument_ids),
            "trade_count": len(trades),
        },
    )


def _trade_cash_ledger_values(
    trade: Trade,
    instrument: Instrument,
    portfolio: Portfolio,
    fx_rates: dict,
) -> dict:
    native_price = trade.executed_price or Decimal("0")
    price = _trade_price_in_base(trade, instrument, portfolio, fx_rates)
    trade_value = money(trade.quantity * price)
    amount = -(trade_value + trade.fees)
    if trade.side == TradeSide.SELL.value:
        amount = trade_value - trade.fees

    return {
        "entry_date": trade.trade_date.date(),
        "amount": amount,
        "currency": portfolio.base_currency,
        "entry_type": f"trade_{trade.side}",
        "platform": trade.broker_reference or "manual",
        "description": (
            f"{trade.side.upper()} {trade.quantity} {instrument.ticker} @ {native_price}"
        ),
        "source_reference": _trade_source_reference(trade.id),
    }


async def _ensure_fx_rates(
    session: AsyncSession,
    *,
    portfolio: Portfolio,
    instruments: list[Instrument],
) -> dict:
    fx_rates = await load_fx_rates(session)
    base = portfolio.base_currency.strip().upper()
    needs_fx = any(
        instrument.currency.strip().upper() != base for instrument in instruments
    )
    if needs_fx and fx_rates.get(("USD", "NGN")) is None:
        await refresh_fx_rates(session)
        fx_rates = await load_fx_rates(session)
    return fx_rates


def _trade_price_in_base(
    trade: Trade,
    instrument: Instrument,
    portfolio: Portfolio,
    fx_rates: dict,
) -> Decimal:
    native_price = trade.executed_price or Decimal("0")
    converted = price_in_portfolio_base(
        native_price,
        instrument,
        portfolio.base_currency,
        fx_rates,
    )
    if converted is None:
        logger.warning(
            "trade_price_not_converted",
            extra={
                "trade_id": str(trade.id),
                "ticker": instrument.ticker,
                "instrument_currency": instrument.currency,
                "portfolio_base": portfolio.base_currency,
            },
        )
        return native_price
    return converted


def _trade_source_reference(trade_id: UUID) -> str:
    return f"manual_trade:{trade_id}"


async def _ensure_default_risk_limits(
    session: AsyncSession, portfolio: Portfolio
) -> None:
    existing_limit_types = set(
        await session.scalars(
            select(RiskLimit.limit_type).where(RiskLimit.portfolio_id == portfolio.id)
        )
    )

    for limit in DEFAULT_RISK_LIMITS:
        if limit.limit_type in existing_limit_types:
            continue

        session.add(
            RiskLimit(
                portfolio_id=portfolio.id,
                name=limit.name,
                limit_type=limit.limit_type,
                threshold_value=limit.threshold_value,
                unit=limit.unit,
                scope=limit.scope,
                severity=limit.severity,
                is_active=True,
                notes="Seeded from phase-one risk limits in SCOPE.md.",
            )
        )
        logger.info(
            "risk_limit_seeded",
            extra={
                "portfolio_id": str(portfolio.id),
                "limit_type": limit.limit_type,
                "threshold_value": str(limit.threshold_value),
            },
        )


async def _list_cash_entries(
    session: AsyncSession, portfolio_id
) -> list[CashLedgerEntry]:
    result = await session.scalars(
        select(CashLedgerEntry)
        .where(CashLedgerEntry.portfolio_id == portfolio_id)
        .order_by(CashLedgerEntry.entry_date.desc(), CashLedgerEntry.created_at.desc())
    )
    return list(result)


async def _list_positions(session: AsyncSession, portfolio_id) -> list[Position]:
    result = await session.scalars(
        select(Position)
        .options(selectinload(Position.instrument))
        .where(Position.portfolio_id == portfolio_id)
        .order_by(Position.market_value.desc())
    )
    return list(result)


async def _list_trades(
    session: AsyncSession,
    portfolio_id,
    *,
    limit: int | None = None,
) -> list[Trade]:
    statement = (
        select(Trade)
        .options(selectinload(Trade.instrument))
        .where(Trade.portfolio_id == portfolio_id)
        .order_by(Trade.trade_date.desc(), Trade.created_at.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)

    result = await session.scalars(statement)
    return list(result)


async def _list_risk_limits(session: AsyncSession, portfolio_id) -> list[RiskLimit]:
    result = await session.scalars(
        select(RiskLimit)
        .where(RiskLimit.portfolio_id == portfolio_id, RiskLimit.is_active.is_(True))
        .order_by(RiskLimit.scope.asc(), RiskLimit.name.asc())
    )
    return list(result)


async def _latest_price_timestamp(
    session: AsyncSession,
    positions: list[Position],
) -> datetime | None:
    instrument_ids = {
        position.instrument_id for position in positions if position.quantity > 0
    }
    if not instrument_ids:
        return None
    return await session.scalar(
        select(func.max(InstrumentQuote.as_of)).where(
            InstrumentQuote.instrument_id.in_(instrument_ids)
        )
    )


def _position_response(position: Position) -> PositionResponse:
    return PositionResponse(
        id=position.id,
        instrument=InstrumentResponse.model_validate(position.instrument),
        quantity=position.quantity,
        average_cost=position.average_cost,
        market_value=position.market_value,
        unrealized_pnl=position.unrealized_pnl,
    )


def _trade_response(trade: Trade) -> TradeResponse:
    return TradeResponse(
        id=trade.id,
        instrument=InstrumentResponse.model_validate(trade.instrument),
        trade_date=trade.trade_date,
        side=trade.side,
        status=trade.status,
        quantity=trade.quantity,
        executed_price=trade.executed_price,
        fees=trade.fees,
        rationale=trade.rationale,
        risk_notes=trade.risk_notes,
        broker_reference=trade.broker_reference,
    )


def _trade_journal_entry_response(
    trade: Trade,
    portfolio: Portfolio,
    fx_rates: dict,
) -> TradeJournalEntryResponse:
    native_price = trade.executed_price or Decimal("0")
    base_price = _trade_price_in_base(trade, trade.instrument, portfolio, fx_rates)
    notional_value = money(trade.quantity * base_price)
    fees_in_base = money(
        _amount_in_portfolio_base(
            trade.fees, trade.instrument, portfolio, fx_rates
        )
    )
    native_notional = trade.quantity * native_price
    cash_impact = _trade_cash_impact(trade, notional_value, fees_in_base)
    fee_bps = None
    if native_notional > 0:
        fee_bps = ((trade.fees / native_notional) * Decimal("10000")).quantize(
            Decimal("0.01")
        )

    return TradeJournalEntryResponse(
        id=trade.id,
        instrument=InstrumentResponse.model_validate(trade.instrument),
        trade_date=trade.trade_date,
        side=trade.side,
        status=trade.status,
        quantity=trade.quantity,
        executed_price=trade.executed_price,
        fees=trade.fees,
        rationale=trade.rationale,
        risk_notes=trade.risk_notes,
        broker_reference=trade.broker_reference,
        notional_value=notional_value,
        cash_impact=cash_impact,
        fees_in_base=fees_in_base,
        fee_bps=fee_bps,
        has_risk_notes=bool(trade.risk_notes and trade.risk_notes.strip()),
    )


def _trade_journal_summary(
    entries: list[TradeJournalEntryResponse],
) -> TradeJournalSummaryResponse:
    total_notional = money(
        sum((entry.notional_value for entry in entries), Decimal("0"))
    )
    total_fees = money(sum((entry.fees_in_base for entry in entries), Decimal("0")))
    net_cash_impact = money(sum((entry.cash_impact for entry in entries), Decimal("0")))
    fee_bps_values = [entry.fee_bps for entry in entries if entry.fee_bps is not None]
    average_fee_bps = None
    if fee_bps_values:
        average_fee_bps = (
            sum(fee_bps_values, Decimal("0")) / Decimal(len(fee_bps_values))
        ).quantize(Decimal("0.01"))

    return TradeJournalSummaryResponse(
        total_trades=len(entries),
        buy_count=len(
            [entry for entry in entries if entry.side == TradeSide.BUY.value]
        ),
        sell_count=len(
            [entry for entry in entries if entry.side == TradeSide.SELL.value]
        ),
        unique_tickers=len({entry.instrument.ticker for entry in entries}),
        gross_traded_value=total_notional,
        net_cash_impact=net_cash_impact,
        total_fees=total_fees,
        average_fee_bps=average_fee_bps,
        last_trade_at=entries[0].trade_date if entries else None,
    )


def _trade_cash_impact(
    trade: Trade, notional_value: Decimal, fees: Decimal | None = None
) -> Decimal:
    trade_fees = trade.fees if fees is None else fees
    if trade.side == TradeSide.SELL.value:
        return money(notional_value - trade_fees)
    return money(-(notional_value + trade_fees))


def _amount_in_portfolio_base(
    amount: Decimal,
    instrument: Instrument,
    portfolio: Portfolio,
    fx_rates: dict,
) -> Decimal:
    converted = price_in_portfolio_base(
        amount,
        instrument,
        portfolio.base_currency,
        fx_rates,
    )
    if converted is None:
        return amount
    return converted


def _risk_limit_snapshot(limit: RiskLimit) -> RiskLimitSnapshot:
    return RiskLimitSnapshot(
        name=limit.name,
        limit_type=limit.limit_type,
        threshold_value=limit.threshold_value,
        unit=limit.unit,
        scope=limit.scope,
        severity=limit.severity,
    )
