import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
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
    Portfolio,
    Position,
    RiskLimit,
    Trade,
    TradeSide,
    TradeStatus,
)
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
    entries = [_trade_journal_entry_response(trade) for trade in trades]
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
    trade_value = money(payload.quantity * payload.price)
    cash_amount = -(trade_value + payload.fees)
    if payload.side == TradeSide.SELL.value:
        cash_amount = trade_value - payload.fees

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
        rationale=payload.rationale,
        risk_notes=payload.risk_notes,
        broker_reference=payload.broker_reference,
    )
    session.add(trade)
    session.add(
        CashLedgerEntry(
            portfolio_id=portfolio.id,
            entry_date=payload.trade_date.date(),
            amount=cash_amount,
            currency=instrument.currency,
            entry_type=f"trade_{payload.side}",
            platform=payload.broker_reference or "manual",
            description=f"{payload.side.upper()} {payload.quantity} {instrument.ticker} @ {payload.price}",
            source_reference="manual_trade",
        )
    )

    await _apply_trade_to_position(session, portfolio, instrument, payload)
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
            "cash_amount": str(cash_amount),
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

    position.market_value = money(position.quantity * payload.price)
    position.unrealized_pnl = money(
        (payload.price - position.average_cost) * position.quantity
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

    result = await session.scalars(
        statement
    )
    return list(result)


async def _list_risk_limits(session: AsyncSession, portfolio_id) -> list[RiskLimit]:
    result = await session.scalars(
        select(RiskLimit)
        .where(RiskLimit.portfolio_id == portfolio_id, RiskLimit.is_active.is_(True))
        .order_by(RiskLimit.scope.asc(), RiskLimit.name.asc())
    )
    return list(result)


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


def _trade_journal_entry_response(trade: Trade) -> TradeJournalEntryResponse:
    price = trade.executed_price or Decimal("0")
    notional_value = money(trade.quantity * price)
    cash_impact = _trade_cash_impact(trade, notional_value)
    fee_bps = None
    if notional_value > 0:
        fee_bps = ((trade.fees / notional_value) * Decimal("10000")).quantize(
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
        fee_bps=fee_bps,
        has_risk_notes=bool(trade.risk_notes and trade.risk_notes.strip()),
    )


def _trade_journal_summary(
    entries: list[TradeJournalEntryResponse],
) -> TradeJournalSummaryResponse:
    total_notional = money(
        sum((entry.notional_value for entry in entries), Decimal("0"))
    )
    total_fees = money(sum((entry.fees for entry in entries), Decimal("0")))
    net_cash_impact = money(
        sum((entry.cash_impact for entry in entries), Decimal("0"))
    )
    fee_bps_values = [
        entry.fee_bps for entry in entries if entry.fee_bps is not None
    ]
    average_fee_bps = None
    if fee_bps_values:
        average_fee_bps = (
            sum(fee_bps_values, Decimal("0")) / Decimal(len(fee_bps_values))
        ).quantize(Decimal("0.01"))

    return TradeJournalSummaryResponse(
        total_trades=len(entries),
        buy_count=len([entry for entry in entries if entry.side == TradeSide.BUY.value]),
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


def _trade_cash_impact(trade: Trade, notional_value: Decimal) -> Decimal:
    if trade.side == TradeSide.SELL.value:
        return money(notional_value - trade.fees)
    return money(-(notional_value + trade.fees))


def _risk_limit_snapshot(limit: RiskLimit) -> RiskLimitSnapshot:
    return RiskLimitSnapshot(
        name=limit.name,
        limit_type=limit.limit_type,
        threshold_value=limit.threshold_value,
        unit=limit.unit,
        scope=limit.scope,
        severity=limit.severity,
    )
