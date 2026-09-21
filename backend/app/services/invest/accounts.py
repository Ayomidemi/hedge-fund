from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.invest import (
    InvestAccountResponse,
    InvestAllocationBucket,
    InvestCashRequest,
    InvestHolding,
    InvestHomeResponse,
    InvestInstrumentResearchResponse,
    InvestInstrumentResponse,
    InvestOrderCreate,
    InvestOrderResponse,
    InvestProfileActivityResponse,
    InvestProfilePermissionResponse,
    InvestProfileResponse,
    InvestResearchMetricResponse,
    InvestResearchSectionResponse,
    InvestTransactionResponse,
    InvestWatchlistItemResponse,
)
from app.api.schemas.operating_core import InstrumentCreate
from app.api.schemas.ticker_intelligence import TickerSuggestionResponse
from app.core.auth import (
    AuthenticatedUser,
    user_can_access_capital,
    user_can_switch_products,
)
from app.core.config import settings
from app.models import (
    Instrument,
    InstrumentQuote,
    RetailAccount,
    RetailOrder,
    RetailWatchlistItem,
    SystemLogEntry,
)
from app.services.administration.system_log import record_system_log
from app.services.brokerage.gateway import get_broker_provider
from app.services.brokerage.paper import PaperBrokerProvider
from app.services.brokerage.protocol import (
    BrokerValidationError,
    CashRequest,
    SubmitOrderRequest,
)
from app.services.invest.fixed_income import (
    ensure_fixed_income_instrument,
    fixed_income_price_per_face,
    fixed_income_quote,
    get_fixed_income_product,
    search_fixed_income_products,
)
from app.services.invest.risk import evaluate_order_risk
from app.services.market_data.quote_cache import (
    get_cached_quote_price,
    get_or_fetch_quote_price,
)
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
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="invest",
        event="retail_account_created",
        message=f"Pease Invest paper account {account.account_number} created.",
        context={
            "account_id": str(account.id),
            "broker_provider": account.broker_provider,
            "starting_cash": str(starting),
        },
    )
    return account


async def get_account_response(
    session: AsyncSession, user: AuthenticatedUser
) -> InvestAccountResponse:
    account = await get_or_create_account(session, user)
    broker = get_broker_provider(session, account.broker_provider)
    snapshot = await broker.get_account(account.broker_account_id)
    return _account_response(
        account,
        snapshot.balances.cash,
        snapshot.balances.buying_power,
    )


async def get_profile(
    session: AsyncSession, user: AuthenticatedUser
) -> InvestProfileResponse:
    account = await get_or_create_account(session, user)
    broker = get_broker_provider(session, account.broker_provider)
    snapshot = await broker.get_account(account.broker_account_id)
    activity = list(
        await session.scalars(
            select(SystemLogEntry)
            .where(SystemLogEntry.owner_user_id == user.id)
            .where(SystemLogEntry.category == "invest")
            .order_by(SystemLogEntry.created_at.desc())
            .limit(8)
        )
    )
    return InvestProfileResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        account=_account_response(
            account,
            snapshot.balances.cash,
            snapshot.balances.buying_power,
        ),
        permissions=_profile_permissions(user),
        product_boundary=[
            "Invest cash stays separate.",
            "Paper orders stay in Invest.",
            "Capital signals stay in Capital.",
            "Broker routing is isolated.",
        ],
        notification_settings=[
            "Order fills",
            "Cash events",
            "Account events",
            "Market alerts planned",
        ],
        recent_activity=[
            InvestProfileActivityResponse(
                event=row.event,
                message=row.message,
                occurred_at=row.created_at,
                level=row.level,
            )
            for row in activity
        ],
    )


async def list_activity(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    limit: int = 100,
) -> list[InvestProfileActivityResponse]:
    rows = list(
        await session.scalars(
            select(SystemLogEntry)
            .where(SystemLogEntry.owner_user_id == user.id)
            .where(SystemLogEntry.category == "invest")
            .order_by(SystemLogEntry.created_at.desc())
            .limit(limit)
        )
    )
    return [
        InvestProfileActivityResponse(
            event=row.event,
            message=row.message,
            occurred_at=row.created_at,
            level=row.level,
        )
        for row in rows
    ]


async def get_home(
    session: AsyncSession, user: AuthenticatedUser
) -> InvestHomeResponse:
    account = await get_or_create_account(session, user)
    broker = get_broker_provider(session, account.broker_provider)
    balances = await broker.get_balances(account.broker_account_id)
    broker_positions = await broker.get_positions(account.broker_account_id)
    holdings = await _holdings(session, broker_positions)
    invested = sum((item.market_value for item in holdings), Decimal("0")).quantize(
        MONEY
    )
    portfolio_value = (balances.cash + invested).quantize(MONEY)
    if portfolio_value > 0:
        for holding in holdings:
            holding.allocation_pct = (
                (holding.market_value / portfolio_value) * Decimal("100")
            ).quantize(Decimal("0.01"))
    total_return = sum(
        (item.unrealized_pnl for item in holdings), Decimal("0")
    ).quantize(MONEY)
    cost_basis = sum(
        (item.market_value - item.unrealized_pnl for item in holdings), Decimal("0")
    )
    return InvestHomeResponse(
        account=_account_response(account, balances.cash, balances.buying_power),
        portfolio_value=portfolio_value,
        cash=balances.cash,
        invested=invested,
        total_return=total_return,
        total_return_pct=(
            ((total_return / cost_basis) * Decimal("100")).quantize(
                Decimal("0.01")
            )
            if cost_basis > 0
            else None
        ),
        allocation=_allocation_buckets(holdings, balances.cash, portfolio_value),
        holdings=holdings,
        headlines=[
            "Discover shows unusual listed-name tape — not a recommendation.",
            "Headlines for your book live on News. Bills and bonds stay on Markets.",
            "Add watchlist names to see when something you follow starts to move.",
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
    instrument = await _require_instrument(session, payload.ticker)
    risk_assessment = evaluate_order_risk(
        account=account,
        instrument=instrument,
        payload=payload,
    )
    if risk_assessment.blockers:
        raise InvestValidationError(
            " ".join(check.message for check in risk_assessment.blockers)
        )
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
    merged_warnings = list(
        dict.fromkeys([*list(order.warnings or []), *risk_assessment.warnings])
    )
    order.warnings = merged_warnings
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="invest",
        event="retail_order_submitted",
        message=f"Paper {order.side.lower()} order for {instrument.ticker} filled.",
        context={
            "account_id": str(account.id),
            "order_id": str(order.id),
            "ticker": instrument.ticker,
            "status": order.status,
            "notional": str(order.notional),
            "quantity": str(order.quantity),
            "risk_checks": [
                {
                    "code": check.code,
                    "level": check.level,
                    "passed": check.passed,
                    "message": check.message,
                }
                for check in risk_assessment.checks
            ],
        },
    )
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
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="invest",
        event="retail_order_cancel_requested",
        message=f"Cancel requested for Pease Invest order {order.id}.",
        context={
            "account_id": str(account.id),
            "order_id": str(order.id),
            "ticker": instrument.ticker,
            "broker_order_id": order.broker_order_id,
        },
    )
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
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="invest",
        event="retail_cash_deposit",
        message="Paper cash added to Pease Invest account.",
        context={
            "account_id": str(account.id),
            "amount": str(payload.amount),
            "currency": account.base_currency,
        },
    )
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
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="invest",
        event="retail_paper_account_reset",
        message="Pease Invest paper account reset.",
        context={
            "account_id": str(account.id),
            "starting_cash": str(settings.invest_paper_starting_cash),
        },
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
        product = get_fixed_income_product(row.instrument.ticker)
        quote = (
            None
            if product is not None
            else await _quote_for_instrument(session, row.instrument)
        )
        items.append(_watchlist_response(row, product=product, quote=quote))
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
        existing_product = get_fixed_income_product(existing.instrument.ticker)
        existing_quote = (
            None
            if existing_product is not None
            else await _quote_for_instrument(session, existing.instrument)
        )
        return _watchlist_response(
            existing,
            product=existing_product,
            quote=existing_quote,
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
    product = get_fixed_income_product(instrument.ticker)
    quote = (
        None
        if product is not None
        else await _quote_for_instrument(session, instrument)
    )
    return InvestWatchlistItemResponse(
        id=item.id,
        ticker=instrument.ticker,
        name=instrument.name,
        asset_class=instrument.asset_class,
        currency=instrument.currency,
        href=_instrument_href(instrument.ticker),
        notes=item.notes,
        date_added=item.date_added,
        price=(
            fixed_income_price_per_face(product)
            if product is not None
            else quote.price
            if quote is not None
            else None
        ),
        change_pct=None if product is not None or quote is None else quote.change_pct,
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
    results: list[InvestInstrumentResponse] = []
    seen: set[str] = set()
    for product in search_fixed_income_products(query, market=market):
        if product.ticker in seen:
            continue
        results.append(
            InvestInstrumentResponse(
                ticker=product.ticker,
                name=product.name,
                asset_class=product.asset_class,
                exchange=product.exchange,
                currency=product.currency,
                sector="Fixed Income",
                industry=product.instrument_type,
                price=fixed_income_price_per_face(product),
            )
        )
        seen.add(product.ticker)

    suggestions = await search_ticker_suggestions(session, query, market_hint=market)
    for item in suggestions:
        if item.ticker in seen:
            continue
        await _ensure_search_instrument(session, item)
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
        seen.add(item.ticker)
    return results


async def _ensure_search_instrument(
    session: AsyncSession,
    item: TickerSuggestionResponse,
) -> Instrument:
    instrument = await session.scalar(
        select(Instrument).where(Instrument.ticker == item.ticker)
    )
    if instrument is not None:
        return instrument
    return await upsert_instrument(
        session,
        InstrumentCreate(
            ticker=item.ticker,
            name=item.name,
            asset_class=item.asset_class,
            exchange=item.exchange,
            currency=item.currency,
            sector=item.sector,
            industry=item.industry,
        ),
    )


async def get_instrument(
    session: AsyncSession, ticker: str
) -> InvestInstrumentResponse:
    instrument = await _require_instrument(session, ticker)
    product = get_fixed_income_product(instrument.ticker)
    if product is not None:
        return InvestInstrumentResponse(
            ticker=instrument.ticker,
            name=instrument.name,
            asset_class=instrument.asset_class,
            exchange=instrument.exchange,
            currency=instrument.currency,
            sector=instrument.sector,
            industry=instrument.industry,
            price=fixed_income_price_per_face(product),
        )
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


async def get_instrument_research(
    session: AsyncSession, ticker: str
) -> InvestInstrumentResearchResponse:
    instrument = await _require_instrument(session, ticker)
    product = get_fixed_income_product(instrument.ticker)
    if product is not None:
        quote = fixed_income_quote(product)
        return InvestInstrumentResearchResponse(
            ticker=instrument.ticker,
            name=instrument.name,
            generated_at=datetime.now(timezone.utc),
            overview=(
                f"{product.name} is modeled as a retail fixed-income paper product. "
                "The view focuses on yield, settlement, accrued interest, cashflows, "
                "minimum order size, and liquidity rather than Capital portfolio alpha."
            ),
            sections=[
                InvestResearchSectionResponse(
                    id="income_profile",
                    title="Income profile",
                    summary=(
                        "Core fixed-income terms used by the paper order and cashflow model."
                    ),
                    metrics=[
                        InvestResearchMetricResponse(
                            label="Issuer",
                            value=product.issuer,
                        ),
                        InvestResearchMetricResponse(
                            label="Instrument",
                            value=product.instrument_type.replace("_", " "),
                        ),
                        InvestResearchMetricResponse(label="Tenor", value=product.tenor),
                        InvestResearchMetricResponse(
                            label="Risk level",
                            value=product.risk_level,
                            tone=_risk_tone(product.risk_level),
                        ),
                    ],
                    notes=list(product.retail_notes),
                ),
                InvestResearchSectionResponse(
                    id="pricing",
                    title="Pricing and settlement",
                    summary=(
                        "Indicative modeled pricing for retail paper execution."
                    ),
                    metrics=[
                        InvestResearchMetricResponse(
                            label="Yield to maturity",
                            value=_pct_text(quote.yield_to_maturity_pct),
                            tone="income",
                        ),
                        InvestResearchMetricResponse(
                            label="Dirty price / 100",
                            value=_money_text(
                                quote.dirty_price_per_100,
                                product.currency,
                                places="0.0001",
                            ),
                        ),
                        InvestResearchMetricResponse(
                            label="Accrued interest / 100",
                            value=_money_text(
                                quote.accrued_interest_per_100,
                                product.currency,
                                places="0.0001",
                            ),
                        ),
                        InvestResearchMetricResponse(
                            label="Settlement",
                            value=quote.settlement_date,
                        ),
                    ],
                    notes=[
                        product.expected_payout,
                        "The price is a deterministic model for paper trading, not a live auction quote.",
                    ],
                ),
                InvestResearchSectionResponse(
                    id="access",
                    title="Retail access",
                    summary=(
                        "Tradeability and order sizing constraints for the Invest paper account."
                    ),
                    metrics=[
                        InvestResearchMetricResponse(
                            label="Trade status",
                            value=product.trade_status.replace("_", " "),
                            tone="positive"
                            if product.trade_status == "paper_tradable"
                            else "neutral",
                        ),
                        InvestResearchMetricResponse(
                            label="Minimum order",
                            value=_money_text(
                                product.minimum_order_amount,
                                product.currency,
                            ),
                        ),
                        InvestResearchMetricResponse(
                            label="Face increment",
                            value=_money_text(
                                product.face_value_increment,
                                product.currency,
                            ),
                        ),
                        InvestResearchMetricResponse(
                            label="Liquidity",
                            value=product.liquidity,
                        ),
                    ],
                    notes=[
                        "Face value and cash impact are isolated to the Invest paper brokerage ledger.",
                        "Proxy ETFs are shown only when there is a clear retail-listed equivalent.",
                    ],
                ),
            ],
            withheld_capital_signals=_withheld_capital_signals(),
            news_href=None,
        )

    from app.services.invest.research import build_listed_research

    return await build_listed_research(session, instrument)


async def _require_instrument(session: AsyncSession, ticker: str) -> Instrument:
    normalized = ticker.strip().upper()
    product = get_fixed_income_product(normalized)
    if product is not None:
        return await ensure_fixed_income_instrument(session, product)
    instrument = await session.scalar(
        select(Instrument).where(Instrument.ticker == normalized)
    )
    if instrument is not None:
        return instrument
    return await upsert_instrument(
        session,
        InstrumentCreate(ticker=normalized, name=normalized, asset_class="other"),
    )


async def _holdings(session: AsyncSession, positions) -> list[InvestHolding]:
    holdings: list[InvestHolding] = []
    for item in positions:
        instrument = await session.scalar(
            select(Instrument).where(Instrument.ticker == item.symbol)
        )
        product = None if instrument is None else get_fixed_income_product(instrument.ticker)
        holdings.append(
            InvestHolding(
                ticker=item.symbol,
                name=instrument.name if instrument is not None else item.symbol,
                asset_class=instrument.asset_class if instrument is not None else None,
                currency=instrument.currency if instrument is not None else "USD",
                quantity=item.quantity,
                average_cost=item.average_cost,
                current_price=(
                    None
                    if instrument is None
                    else fixed_income_price_per_face(product)
                    if product is not None
                    else await get_cached_quote_price(session, item.symbol)
                ),
                market_value=item.market_value,
                allocation_pct=None,
                unrealized_pnl=item.unrealized_pnl,
                unrealized_pnl_pct=item.unrealized_pnl_pct,
                href=_instrument_href(item.symbol),
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
        asset_class=instrument.asset_class,
        currency=instrument.currency,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        notional=order.notional,
        status=order.status,
        submitted_at=order.submitted_at,
        filled_at=order.filled_at,
        average_fill_price=order.average_fill_price,
        filled_quantity=order.filled_quantity,
        broker_provider=order.broker_provider,
        broker_order_id=order.broker_order_id,
        warnings=list(order.warnings or []),
    )


def _profile_permissions(user: AuthenticatedUser) -> list[InvestProfilePermissionResponse]:
    return [
        InvestProfilePermissionResponse(
            code="paper_trading",
            label="Paper trading",
            enabled=True,
            description="Simulated Invest orders.",
        ),
        InvestProfilePermissionResponse(
            code="fixed_income",
            label="Fixed income",
            enabled=True,
            description="Bills, notes, bonds, and cash-yield products.",
        ),
        InvestProfilePermissionResponse(
            code="real_cash_movements",
            label="Real cash movement",
            enabled=False,
            description="Live funding is off.",
        ),
        InvestProfilePermissionResponse(
            code="capital_workspace",
            label="Pease Capital workspace",
            enabled=user_can_access_capital(user),
            description="Fund books and PM workflow.",
        ),
        InvestProfilePermissionResponse(
            code="product_switching",
            label="Product switching",
            enabled=user_can_switch_products(user),
            description="Invest and Capital switcher.",
        ),
    ]


def _withheld_capital_signals() -> list[str]:
    return [
        "Capital target weights",
        "Expected alpha and model rank",
        "Strategy pod assignment",
        "PM approval state",
        "Portfolio hedge recommendation",
        "Fund-level risk budget",
    ]


def _money_text(
    value: Decimal | None,
    currency: str,
    *,
    places: str = "0.01",
) -> str:
    if value is None:
        return "Unavailable"
    return f"{currency} {value.quantize(Decimal(places))}"


def _pct_text(value: Decimal | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{value.quantize(Decimal('0.01'))}%"


def _change_tone(value: Decimal | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _risk_tone(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "low":
        return "positive"
    if normalized == "high":
        return "negative"
    return "neutral"


def _quote_status(quote: InstrumentQuote | None) -> str:
    if quote is None:
        return "Unavailable"
    if quote.is_stale:
        return f"Stale as of {quote.as_of.isoformat()}"
    return f"Fresh as of {quote.as_of.isoformat()}"


def _account_number() -> str:
    return f"PI-{uuid4().hex[:8].upper()}"


async def _quote_for_instrument(
    session: AsyncSession, instrument: Instrument
) -> InstrumentQuote | None:
    return await session.scalar(
        select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument.id)
    )


def _watchlist_response(
    row: RetailWatchlistItem,
    *,
    product,
    quote: InstrumentQuote | None,
) -> InvestWatchlistItemResponse:
    instrument = row.instrument
    return InvestWatchlistItemResponse(
        id=row.id,
        ticker=instrument.ticker,
        name=instrument.name,
        asset_class=instrument.asset_class,
        currency=instrument.currency,
        href=_instrument_href(instrument.ticker),
        notes=row.notes,
        date_added=row.date_added,
        price=(
            fixed_income_price_per_face(product)
            if product is not None
            else quote.price
            if quote is not None
            else None
        ),
        change_pct=None if product is not None or quote is None else quote.change_pct,
    )


def _instrument_href(ticker: str) -> str:
    return (
        f"/invest/fixed-income/{ticker}"
        if get_fixed_income_product(ticker) is not None
        else f"/invest/instruments/{ticker}"
    )


def _allocation_buckets(
    holdings: list[InvestHolding],
    cash: Decimal,
    portfolio_value: Decimal,
) -> list[InvestAllocationBucket]:
    buckets: dict[str, Decimal] = {"Cash": cash}
    for holding in holdings:
        name = _allocation_name(holding.asset_class)
        buckets[name] = buckets.get(name, Decimal("0")) + holding.market_value

    if portfolio_value <= 0:
        return [
            InvestAllocationBucket(
                name=name,
                value=value.quantize(MONEY),
                allocation_pct=Decimal("0.00"),
            )
            for name, value in buckets.items()
            if value > 0
        ]

    return [
        InvestAllocationBucket(
            name=name,
            value=value.quantize(MONEY),
            allocation_pct=((value / portfolio_value) * Decimal("100")).quantize(
                Decimal("0.01")
            ),
        )
        for name, value in buckets.items()
        if value > 0
    ]


def _allocation_name(asset_class: str | None) -> str:
    normalized = (asset_class or "Other").strip().lower()
    if normalized in {"cash_equivalent", "bond"}:
        return "Fixed income"
    if normalized == "etf":
        return "ETFs"
    if normalized == "equity":
        return "Stocks"
    return normalized.replace("_", " ").title()
