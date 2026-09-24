from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
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
    InvestQuickActionResponse,
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
    RadarSnapshot,
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
    fixed_income_price_per_face_db,
    fixed_income_products_by_tickers_db,
    get_fixed_income_product,
    get_fixed_income_product_db,
    latest_fixed_income_quote,
    search_fixed_income_products_db,
)
from app.services.invest.configuration import (
    default_invest_setting,
    get_home_quick_actions,
    get_profile_policy,
    get_typed_risk_policy,
)
from app.services.invest.risk import evaluate_order_risk
from app.services.market_data.fx_convert import amount_in_base, convert_amount_to_base
from app.services.market_data.fx_refresh import load_fx_rates
from app.services.market_data.quote_cache import get_cached_quote_price
from app.services.market_radar.watchlist_book import (
    WatchlistValidationError,
    get_ticker_chart,
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
    profile_policy = await get_profile_policy(session)
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
        permissions=_profile_permissions(user, profile_policy.get("permissions")),
        product_boundary=list(profile_policy.get("product_boundary") or []),
        notification_settings=list(profile_policy.get("notification_settings") or []),
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
    holdings = await _holdings(session, broker_positions, account.base_currency)
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
    today_change, today_change_pct = await _today_change(session, holdings, invested)
    headlines = await _home_headlines(session, today_change, account.base_currency)
    quick_actions = [
        InvestQuickActionResponse.model_validate(action)
        for action in await get_home_quick_actions(session)
    ]
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
        today_change=today_change,
        today_change_pct=today_change_pct,
        allocation=_allocation_buckets(holdings, balances.cash, portfolio_value),
        holdings=holdings,
        headlines=headlines,
        quick_actions=quick_actions,
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
    fixed_income_product = await get_fixed_income_product_db(session, instrument.ticker)
    if fixed_income_product is not None:
        instrument = await ensure_fixed_income_instrument(session, fixed_income_product)
    risk_policy = await get_typed_risk_policy(session)
    cash_notional = await _cash_notional_for_order(
        session, account, instrument, fixed_income_product, payload.amount
    )
    risk_assessment = evaluate_order_risk(
        account=account,
        instrument=instrument,
        payload=payload,
        fixed_income_product=fixed_income_product,
        policy=risk_policy,
        cash_notional=cash_notional,
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
    tickers = [row.instrument.ticker for row in rows]
    headlines = await _watchlist_headlines(session, tickers)
    unusual = await _watchlist_unusual(session, tickers)
    quotes = {
        quote.instrument_id: quote
        for quote in await session.scalars(
            select(InstrumentQuote).where(
                InstrumentQuote.instrument_id.in_(
                    [row.instrument.id for row in rows]
                )
            )
        )
    } if rows else {}
    products = await fixed_income_products_by_tickers_db(session, tickers)
    for row in rows:
        product = products.get(row.instrument.ticker.upper())
        quote = None if product is not None else quotes.get(row.instrument.id)
        ticker_key = row.instrument.ticker.upper()
        items.append(
            await _watchlist_response(
                session,
                row,
                product=product,
                quote=quote,
                headline=headlines.get(ticker_key),
                unusual=ticker_key in unusual,
                unusual_label=unusual.get(ticker_key),
            )
        )
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
        existing_product = await get_fixed_income_product_db(
            session, existing.instrument.ticker
        )
        existing_quote = (
            None
            if existing_product is not None
            else await _quote_for_instrument(session, existing.instrument)
        )
        return await _watchlist_response(
            session,
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
    item.instrument = instrument
    session.add(item)
    await session.commit()
    await session.refresh(item)
    item.instrument = instrument
    product = await get_fixed_income_product_db(session, instrument.ticker)
    quote = (
        None
        if product is not None
        else await _quote_for_instrument(session, instrument)
    )
    return await _watchlist_response(
        session,
        item,
        product=product,
        quote=quote,
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
    fixed_income_products = await search_fixed_income_products_db(
        session, query, market=market
    )
    for product in fixed_income_products:
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
                price=await fixed_income_price_per_face_db(session, product),
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
    asset_class = (instrument.asset_class or "").strip().lower()
    if asset_class in {"bond", "cash_equivalent"}:
        product = await get_fixed_income_product_db(session, instrument.ticker)
        if product is not None:
            return InvestInstrumentResponse(
                ticker=instrument.ticker,
                name=instrument.name,
                asset_class=instrument.asset_class,
                exchange=instrument.exchange,
                currency=instrument.currency,
                sector=instrument.sector,
                industry=instrument.industry,
                price=await fixed_income_price_per_face_db(session, product),
            )
    price = await get_cached_quote_price(session, instrument.ticker)
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


async def get_instrument_chart(
    session: AsyncSession, ticker: str, range_key: str = "3m"
):
    try:
        return await get_ticker_chart(
            session, ticker=ticker.strip().upper(), range_key=range_key
        )
    except WatchlistValidationError as exc:
        raise InvestValidationError(str(exc)) from exc


async def get_instrument_research(
    session: AsyncSession, ticker: str
) -> InvestInstrumentResearchResponse:
    instrument = await _require_instrument(session, ticker)
    asset_class = (instrument.asset_class or "").strip().lower()
    product = (
        await get_fixed_income_product_db(session, instrument.ticker)
        if asset_class in {"bond", "cash_equivalent"}
        else None
    )
    if product is not None:
        quote = await latest_fixed_income_quote(session, product)
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
    product = await get_fixed_income_product_db(session, normalized)
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


async def _cash_notional_for_order(
    session: AsyncSession,
    account: RetailAccount,
    instrument: Instrument,
    product,
    amount: Decimal | None,
) -> Decimal | None:
    if amount is None:
        return None
    currency = (product.currency if product is not None else instrument.currency) or (
        account.base_currency
    )
    converted = await convert_amount_to_base(
        session, amount, currency, account.base_currency
    )
    if converted is None:
        raise InvestValidationError(
            f"No {account.base_currency}/{currency} rate available to paper this order."
        )
    return converted


async def _holdings(
    session: AsyncSession, positions, base_currency: str = "USD"
) -> list[InvestHolding]:
    symbols = [item.symbol for item in positions]
    instruments = {
        row.ticker: row
        for row in await session.scalars(
            select(Instrument).where(Instrument.ticker.in_(symbols))
        )
    } if symbols else {}
    products = await fixed_income_products_by_tickers_db(session, symbols)
    quotes = {
        quote.instrument_id: quote
        for quote in await session.scalars(
            select(InstrumentQuote).where(
                InstrumentQuote.instrument_id.in_(
                    [
                        row.id
                        for ticker, row in instruments.items()
                        if ticker not in products
                    ]
                )
            )
        )
    } if instruments else {}
    fx_rates = await load_fx_rates(session)
    holdings: list[InvestHolding] = []
    for item in positions:
        instrument = instruments.get(item.symbol)
        product = products.get(item.symbol.upper())
        quote = (
            None
            if instrument is None
            else quotes.get(instrument.id)
        )
        native_price = (
            None
            if instrument is None
            else await fixed_income_price_per_face_db(session, product)
            if product is not None
            else quote.price
            if quote is not None
            else None
        )
        native_currency = (
            instrument.currency if instrument is not None else base_currency
        )
        price = native_price
        if native_price is not None:
            converted = amount_in_base(
                native_price, native_currency, base_currency, fx_rates
            )
            if converted is not None:
                price = converted
        holdings.append(
            InvestHolding(
                ticker=item.symbol,
                name=instrument.name if instrument is not None else item.symbol,
                asset_class=instrument.asset_class if instrument is not None else None,
                currency=base_currency,
                quantity=item.quantity,
                average_cost=item.average_cost,
                current_price=price,
                market_value=item.market_value,
                allocation_pct=None,
                unrealized_pnl=item.unrealized_pnl,
                unrealized_pnl_pct=item.unrealized_pnl_pct,
                href=_instrument_href(
                    item.symbol,
                    instrument.asset_class if instrument is not None else None,
                ),
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


def _profile_permissions(
    user: AuthenticatedUser, configured: list[dict] | None = None
) -> list[InvestProfilePermissionResponse]:
    entries = configured
    if entries is None:
        profile_policy = default_invest_setting("profile_policy")
        entries = list(profile_policy.get("permissions") or [])
    dynamic_enabled = {
        "capital_workspace": user_can_access_capital(user),
        "product_switching": user_can_switch_products(user),
    }
    return [
        InvestProfilePermissionResponse(
            code=str(entry.get("code", "")),
            label=str(entry.get("label", entry.get("code", ""))),
            enabled=bool(
                dynamic_enabled.get(str(entry.get("code", "")), entry.get("enabled"))
            ),
            description=str(entry.get("description", "")),
        )
        for entry in entries
        if entry.get("code")
    ]


def _withheld_capital_signals(configured: list[str] | None = None) -> list[str]:
    if configured is not None:
        return list(configured)
    profile_policy = default_invest_setting("profile_policy")
    return list(profile_policy.get("withheld_capital_signals") or [])


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


async def _watchlist_response(
    session: AsyncSession,
    row: RetailWatchlistItem,
    *,
    product,
    quote: InstrumentQuote | None,
    headline: str | None = None,
    unusual: bool = False,
    unusual_label: str | None = None,
) -> InvestWatchlistItemResponse:
    instrument = row.instrument
    price = (
        await fixed_income_price_per_face_db(session, product)
        if product is not None
        else quote.price
        if quote is not None
        else None
    )
    return InvestWatchlistItemResponse(
        id=row.id,
        ticker=instrument.ticker,
        name=instrument.name,
        asset_class=instrument.asset_class,
        currency=instrument.currency,
        href=(
            f"/invest/fixed-income/{instrument.ticker}"
            if product is not None
            else _instrument_href(instrument.ticker, instrument.asset_class)
        ),
        notes=row.notes,
        date_added=row.date_added,
        price=price,
        change_pct=None if product is not None or quote is None else quote.change_pct,
        headline=headline,
        unusual=unusual,
        unusual_label=unusual_label,
    )


def _instrument_href(ticker: str, asset_class: str | None = None) -> str:
    klass = (asset_class or "").strip().lower()
    if klass in {"bond", "cash_equivalent"} or get_fixed_income_product(ticker) is not None:
        return f"/invest/fixed-income/{ticker}"
    return f"/invest/instruments/{ticker}"


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


async def _today_change(
    session: AsyncSession,
    holdings: list[InvestHolding],
    invested: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    listed = [
        holding
        for holding in holdings
        if (holding.asset_class or "").strip().lower()
        not in {"bond", "cash_equivalent"}
    ]
    if not listed:
        return None, None
    tickers = [holding.ticker for holding in listed]
    instruments = {
        row.ticker: row
        for row in await session.scalars(
            select(Instrument).where(Instrument.ticker.in_(tickers))
        )
    }
    if not instruments:
        return None, None
    quotes = {
        quote.instrument_id: quote
        for quote in await session.scalars(
            select(InstrumentQuote).where(
                InstrumentQuote.instrument_id.in_(
                    [row.id for row in instruments.values()]
                )
            )
        )
    }
    day_pnl = Decimal("0")
    marked = False
    for holding in listed:
        instrument = instruments.get(holding.ticker)
        if instrument is None:
            continue
        quote = quotes.get(instrument.id)
        if quote is None or quote.change_pct is None:
            continue
        marked = True
        denom = Decimal("100") + quote.change_pct
        if denom == 0:
            continue
        day_pnl += holding.market_value * quote.change_pct / denom
    if not marked:
        return None, None
    day_pnl = day_pnl.quantize(MONEY)
    pct = (
        ((day_pnl / invested) * Decimal("100")).quantize(Decimal("0.01"))
        if invested > 0
        else None
    )
    return day_pnl, pct


async def _home_headlines(
    session: AsyncSession, today_change: Decimal | None, currency: str
) -> list[str]:
    from app.services.invest.discover import home_tape_headline
    from app.services.invest.news import rates_headline

    lines: list[str] = []
    if today_change is None:
        lines.append(
            "No live day mark on listed names yet. Cash and bills use source-labeled fixed-income marks."
        )
    elif today_change > 0:
        lines.append(
            f"Your listed book is up {currency} {today_change.quantize(MONEY)} today."
        )
    elif today_change < 0:
        lines.append(
            f"Your listed book is down {currency} {abs(today_change).quantize(MONEY)} today."
        )
    else:
        lines.append("Your listed book is roughly unchanged today.")
    tape = await home_tape_headline(session)
    if tape:
        lines.append(tape)
    rates = await rates_headline(session)
    if rates:
        lines.append(rates)
    if len(lines) < 3:
        lines.append(
            "Discover is unusual listed-name tape. Rates headlines lead on News."
        )
    return lines[:3]


async def _watchlist_headlines(
    session: AsyncSession, tickers: list[str]
) -> dict[str, str]:
    from app.services.invest.news import headlines_for_tickers

    return await headlines_for_tickers(session, tickers)


async def _watchlist_unusual(
    session: AsyncSession, tickers: list[str]
) -> dict[str, str]:
    wanted = {ticker.upper() for ticker in tickers if ticker}
    if not wanted:
        return {}
    latest = (
        select(
            RadarSnapshot.ticker,
            func.max(RadarSnapshot.as_of).label("as_of"),
        )
        .where(func.upper(RadarSnapshot.ticker).in_(wanted))
        .group_by(RadarSnapshot.ticker)
        .subquery()
    )
    rows = await session.scalars(
        select(RadarSnapshot).join(
            latest,
            (RadarSnapshot.ticker == latest.c.ticker)
            & (RadarSnapshot.as_of == latest.c.as_of),
        )
    )
    found: dict[str, str] = {}
    for row in rows:
        if row.flags:
            found[row.ticker.upper()] = "Unusual"
    return found
