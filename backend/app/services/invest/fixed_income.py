from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.invest import (
    InvestFixedIncomeCashflowResponse,
    InvestFixedIncomeProductResponse,
    InvestRiskCheckResponse,
)
from app.api.schemas.operating_core import InstrumentCreate
from app.models import (
    Instrument,
    InvestFixedIncomeProduct as InvestFixedIncomeProductRecord,
    InvestFixedIncomeQuote as InvestFixedIncomeQuoteRecord,
    InvestYieldCurve,
    InvestYieldCurvePoint,
)
from app.services.invest.fixed_income_providers import (
    IMPLEMENTED_MODEL_PROVIDER,
    QUOTE_QUALITY_SEED_MODEL,
    fixed_income_provider_plan,
    provider_label,
    quote_quality_is_live,
    quote_quality_label,
    stale_after_for_quality,
)
from app.services.portfolio.operating_core import upsert_instrument

logger = logging.getLogger(__name__)

PRICE = Decimal("0.0001")
MONEY = Decimal("0.01")
FACE_VALUE = Decimal("100")
QUOTE_FRESH_FOR = IMPLEMENTED_MODEL_PROVIDER.freshness


@dataclass(frozen=True)
class FixedIncomeProduct:
    ticker: str
    name: str
    market: str
    currency: str
    issuer: str
    instrument_type: str
    tenor: str
    maturity_date: str | None
    maturity_days: int | None
    indicative_yield_pct: Decimal | None
    coupon_rate_pct: Decimal | None
    coupon_frequency_per_year: int
    settlement_days: int
    minimum_order_amount: Decimal
    face_value_increment: Decimal
    liquidity: str
    risk_level: str
    expected_payout: str
    trade_status: str
    asset_class: str
    exchange: str | None
    proxy_ticker: str | None
    proxy_label: str | None
    retail_notes: tuple[str, ...]
    day_count_convention: str = "ACT/365"
    compounding_basis: str = "simple"
    quote_source: str = "model_seed"
    db_id: UUID | None = None


@dataclass(frozen=True)
class FixedIncomeCashflow:
    payment_date: str
    cashflow_type: str
    amount_per_100: Decimal
    description: str


@dataclass(frozen=True)
class FixedIncomeQuote:
    as_of: datetime
    stale_after: datetime
    settlement_date: str
    maturity_date: str
    days_to_maturity: int
    clean_price_per_100: Decimal
    accrued_interest_per_100: Decimal
    dirty_price_per_100: Decimal
    yield_to_maturity_pct: Decimal | None
    next_coupon_date: str | None
    face_value_increment: Decimal
    quote_status: str
    quote_source: str
    quote_provider: str
    quote_provider_label: str
    quote_quality: str
    quote_quality_label: str
    quote_type: str
    quote_is_live: bool
    quote_stale: bool
    pricing_assumptions: tuple[str, ...]
    provider_security_id: str | None = None
    bid_price_per_100: Decimal | None = None
    ask_price_per_100: Decimal | None = None
    mid_price_per_100: Decimal | None = None
    last_price_per_100: Decimal | None = None
    bid_yield_pct: Decimal | None = None
    ask_yield_pct: Decimal | None = None
    mid_yield_pct: Decimal | None = None
    last_yield_pct: Decimal | None = None
    raw_payload: dict = field(default_factory=dict)


_SEED_DIR = Path(__file__).with_name("seed_data")


@lru_cache(maxsize=1)
def _load_seed_fixed_income_products() -> tuple[FixedIncomeProduct, ...]:
    path = _SEED_DIR / "fixed_income_products.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return tuple(_product_from_seed(row) for row in rows)


def _product_from_seed(row: dict) -> FixedIncomeProduct:
    return FixedIncomeProduct(
        ticker=row["ticker"],
        name=row["name"],
        market=row["market"],
        currency=row["currency"],
        issuer=row["issuer"],
        instrument_type=row["instrument_type"],
        tenor=row["tenor"],
        maturity_date=row.get("maturity_date"),
        maturity_days=row.get("maturity_days"),
        indicative_yield_pct=_seed_decimal(row.get("indicative_yield_pct")),
        coupon_rate_pct=_seed_decimal(row.get("coupon_rate_pct")),
        coupon_frequency_per_year=int(row["coupon_frequency_per_year"]),
        settlement_days=int(row["settlement_days"]),
        minimum_order_amount=_seed_decimal(row["minimum_order_amount"]),
        face_value_increment=_seed_decimal(row["face_value_increment"]),
        liquidity=row["liquidity"],
        risk_level=row["risk_level"],
        expected_payout=row["expected_payout"],
        trade_status=row["trade_status"],
        asset_class=row["asset_class"],
        exchange=row.get("exchange"),
        proxy_ticker=row.get("proxy_ticker"),
        proxy_label=row.get("proxy_label"),
        retail_notes=tuple(row.get("retail_notes") or []),
        day_count_convention=row.get("day_count_convention", "ACT/365"),
        compounding_basis=row.get("compounding_basis", "simple"),
        quote_source=row.get("quote_source", "model_seed"),
    )


def _seed_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


FIXED_INCOME_PRODUCTS: tuple[FixedIncomeProduct, ...] = (
    _load_seed_fixed_income_products()
)


def get_fixed_income_product(ticker: str) -> FixedIncomeProduct | None:
    normalized = ticker.strip().upper()
    for product in FIXED_INCOME_PRODUCTS:
        if product.ticker == normalized:
            return product
    return None


async def fixed_income_products_by_tickers_db(
    session: AsyncSession, tickers: list[str]
) -> dict[str, FixedIncomeProduct]:
    wanted = {ticker.strip().upper() for ticker in tickers if ticker and ticker.strip()}
    if not wanted:
        return {}
    if not await ensure_fixed_income_seed_products(session):
        return {
            product.ticker: product
            for product in FIXED_INCOME_PRODUCTS
            if product.ticker in wanted
        }
    try:
        rows = await session.scalars(
            select(InvestFixedIncomeProductRecord).where(
                InvestFixedIncomeProductRecord.ticker.in_(wanted)
            )
        )
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_fixed_income_table(exc):
            raise
        await _rollback_after_fixed_income_fallback(session)
        return {
            product.ticker: product
            for product in FIXED_INCOME_PRODUCTS
            if product.ticker in wanted
        }
    return {row.ticker: _product_from_record(row) for row in rows if row.is_active}


async def get_fixed_income_product_db(
    session: AsyncSession, ticker: str
) -> FixedIncomeProduct | None:
    products = await fixed_income_products_by_tickers_db(session, [ticker])
    return products.get(ticker.strip().upper())


def search_fixed_income_products(
    query: str = "",
    *,
    market: str | None = None,
) -> list[FixedIncomeProduct]:
    normalized_query = query.strip().upper()
    normalized_market = (market or "").strip().upper()
    products: list[FixedIncomeProduct] = []
    for product in FIXED_INCOME_PRODUCTS:
        if normalized_market and normalized_market not in {"ALL", product.market}:
            continue
        haystack = f"{product.ticker} {product.name} {product.issuer} {product.instrument_type}".upper()
        if normalized_query and normalized_query not in haystack:
            continue
        products.append(product)
    return products


async def search_fixed_income_products_db(
    session: AsyncSession,
    query: str = "",
    *,
    market: str | None = None,
) -> list[FixedIncomeProduct]:
    if not await ensure_fixed_income_seed_products(session):
        return search_fixed_income_products(query, market=market)
    normalized_query = query.strip().upper()
    normalized_market = (market or "").strip().upper()
    try:
        rows = list(
            await session.scalars(
                select(InvestFixedIncomeProductRecord)
                .where(InvestFixedIncomeProductRecord.is_active.is_(True))
                .order_by(
                    InvestFixedIncomeProductRecord.market.asc(),
                    InvestFixedIncomeProductRecord.instrument_type.asc(),
                    InvestFixedIncomeProductRecord.ticker.asc(),
                )
            )
        )
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_fixed_income_table(exc):
            raise
        await _rollback_after_fixed_income_fallback(session)
        return search_fixed_income_products(query, market=market)
    products: list[FixedIncomeProduct] = []
    for row in rows:
        if normalized_market and normalized_market not in {"ALL", row.market}:
            continue
        haystack = (
            f"{row.ticker} {row.name} {row.issuer} {row.instrument_type} "
            f"{row.tenor} {row.currency}"
        ).upper()
        if normalized_query and normalized_query not in haystack:
            continue
        products.append(_product_from_record(row))
    return products


async def ensure_fixed_income_seed_products(session: AsyncSession) -> bool:
    default_tickers = [product.ticker for product in FIXED_INCOME_PRODUCTS]
    if not await _fixed_income_table_exists(session, "invest_fixed_income_products"):
        return False
    try:
        existing = {
            ticker
            for ticker in await session.scalars(
                select(InvestFixedIncomeProductRecord.ticker).where(
                    InvestFixedIncomeProductRecord.ticker.in_(default_tickers)
                )
            )
        }
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_fixed_income_table(exc):
            raise
        await _rollback_after_fixed_income_fallback(session)
        return False
    missing = [
        product for product in FIXED_INCOME_PRODUCTS if product.ticker not in existing
    ]
    if not missing:
        return True
    try:
        for product in missing:
            session.add(_record_from_product(product))
        await session.flush()
        rows = list(
            await session.scalars(
                select(InvestFixedIncomeProductRecord).where(
                    InvestFixedIncomeProductRecord.ticker.in_(
                        [product.ticker for product in missing]
                    )
                )
            )
        )
        if not await _fixed_income_table_exists(session, "invest_fixed_income_quotes"):
            return True
        await refresh_fixed_income_quotes(
            session, [_product_from_record(record) for record in rows]
        )
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_fixed_income_table(exc):
            raise
        await _rollback_after_fixed_income_fallback(session)
        return False
    return True


async def refresh_fixed_income_quotes(
    session: AsyncSession,
    products: list[FixedIncomeProduct] | None = None,
) -> list[FixedIncomeQuote]:
    if products is None:
        if not await _fixed_income_table_exists(
            session, "invest_fixed_income_products"
        ):
            products = list(FIXED_INCOME_PRODUCTS)
        else:
            try:
                records = list(
                    await session.scalars(
                        select(InvestFixedIncomeProductRecord).where(
                            InvestFixedIncomeProductRecord.is_active.is_(True)
                        )
                    )
                )
                products = [_product_from_record(record) for record in records]
            except (OperationalError, ProgrammingError) as exc:
                if not _is_missing_fixed_income_table(exc):
                    raise
                await _rollback_after_fixed_income_fallback(session)
                products = list(FIXED_INCOME_PRODUCTS)
    elif not await _fixed_income_table_exists(session, "invest_fixed_income_quotes"):
        return [fixed_income_quote(product) for product in products]

    quotes: list[FixedIncomeQuote] = []
    for product in products:
        quote = await latest_fixed_income_quote(session, product, refresh_if_stale=True)
        quotes.append(quote)
    if await _fixed_income_table_exists(
        session, "invest_yield_curves"
    ) and await _fixed_income_table_exists(session, "invest_yield_curve_points"):
        try:
            await _ensure_model_yield_curves(session, products)
        except (OperationalError, ProgrammingError) as exc:
            if not _is_missing_fixed_income_table(exc):
                raise
            await _rollback_after_fixed_income_fallback(session)
    return quotes


async def latest_fixed_income_quote(
    session: AsyncSession,
    product: FixedIncomeProduct,
    *,
    refresh_if_stale: bool = True,
) -> FixedIncomeQuote:
    if product.db_id is None:
        return fixed_income_quote(product)
    if not await _fixed_income_table_exists(session, "invest_fixed_income_quotes"):
        return fixed_income_quote(product)

    try:
        record = await session.scalar(
            select(InvestFixedIncomeQuoteRecord)
            .where(InvestFixedIncomeQuoteRecord.product_id == product.db_id)
            .order_by(InvestFixedIncomeQuoteRecord.source_as_of.desc())
            .limit(1)
        )
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_fixed_income_table(exc):
            raise
        await _rollback_after_fixed_income_fallback(session)
        return fixed_income_quote(product)
    now = datetime.now(timezone.utc)
    if record is not None:
        stale_after = _aware_datetime(record.stale_after)
    if record is not None and (not refresh_if_stale or stale_after > now):
        return _quote_from_record(product, record, now=now)

    quote = fixed_income_quote(product, as_of=now)
    try:
        session.add(_quote_record_from_quote(product, quote))
        await session.flush()
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_fixed_income_table(exc):
            raise
        await _rollback_after_fixed_income_fallback(session)
    return quote


async def ensure_fixed_income_instrument(
    session: AsyncSession, product: FixedIncomeProduct
) -> Instrument:
    existing = await session.scalar(
        select(Instrument).where(Instrument.ticker == product.ticker)
    )
    if existing is not None:
        return existing
    return await upsert_instrument(
        session,
        InstrumentCreate(
            ticker=product.ticker,
            name=product.name,
            asset_class=product.asset_class,
            exchange=product.exchange,
            currency=product.currency,
            sector="Fixed Income",
            industry=product.instrument_type,
        ),
    )


def fixed_income_quote(
    product: FixedIncomeProduct,
    *,
    as_of: datetime | date | None = None,
) -> FixedIncomeQuote:
    quote_as_of = _as_datetime(as_of)
    trade_date = quote_as_of.date()
    settlement = _add_business_days(trade_date, product.settlement_days)
    maturity = _resolve_maturity_date(product, settlement)
    days_to_maturity = max((maturity - settlement).days, 0)
    annual_yield = (product.indicative_yield_pct or Decimal("0")) / Decimal("100")
    cashflows = _project_cashflows(product, settlement, maturity)

    if product.instrument_type == "treasury_bill":
        clean_price = _discount_bill_price(annual_yield, days_to_maturity)
        accrued_interest = Decimal("0")
        dirty_price = clean_price
        next_coupon_date = None
    else:
        accrued_interest = _accrued_interest(product, settlement, maturity)
        dirty_price = _coupon_bond_dirty_price(product, annual_yield, cashflows)
        clean_price = dirty_price - accrued_interest
        next_coupon_date = next(
            (
                flow.payment_date
                for flow in cashflows
                if flow.cashflow_type in {"coupon", "coupon_principal"}
            ),
            None,
        )
    clean_price_per_100 = _price(clean_price)
    accrued_interest_per_100 = _price(accrued_interest)
    dirty_price_per_100 = _price(dirty_price)
    yield_to_maturity_pct = (
        _percent(product.indicative_yield_pct)
        if product.indicative_yield_pct is not None
        else None
    )
    quote_provider = IMPLEMENTED_MODEL_PROVIDER.provider
    quote_quality = QUOTE_QUALITY_SEED_MODEL
    stale_after = stale_after_for_quality(quote_quality, quote_as_of)

    return FixedIncomeQuote(
        as_of=quote_as_of,
        stale_after=stale_after,
        settlement_date=settlement.isoformat(),
        maturity_date=maturity.isoformat(),
        days_to_maturity=days_to_maturity,
        clean_price_per_100=clean_price_per_100,
        accrued_interest_per_100=accrued_interest_per_100,
        dirty_price_per_100=dirty_price_per_100,
        yield_to_maturity_pct=yield_to_maturity_pct,
        next_coupon_date=next_coupon_date,
        face_value_increment=product.face_value_increment,
        quote_status="indicative_model",
        quote_source=product.quote_source,
        quote_provider=quote_provider,
        quote_provider_label=provider_label(quote_provider),
        quote_quality=quote_quality,
        quote_quality_label=quote_quality_label(quote_quality),
        quote_type="model",
        quote_is_live=quote_quality_is_live(quote_quality),
        quote_stale=False,
        pricing_assumptions=_pricing_assumptions(product),
        mid_price_per_100=dirty_price_per_100,
        mid_yield_pct=yield_to_maturity_pct,
    )


def fixed_income_cashflows(
    product: FixedIncomeProduct,
    *,
    as_of: datetime | date | None = None,
) -> list[FixedIncomeCashflow]:
    quote_as_of = _as_datetime(as_of)
    settlement = _add_business_days(quote_as_of.date(), product.settlement_days)
    maturity = _resolve_maturity_date(product, settlement)
    return _project_cashflows(product, settlement, maturity)


def fixed_income_price_per_face(product: FixedIncomeProduct) -> Decimal:
    quote = fixed_income_quote(product)
    return (quote.dirty_price_per_100 / FACE_VALUE).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )


async def fixed_income_price_per_face_db(
    session: AsyncSession, product: FixedIncomeProduct
) -> Decimal:
    quote = await latest_fixed_income_quote(session, product)
    return (quote.dirty_price_per_100 / FACE_VALUE).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )


async def fixed_income_response_db(
    session: AsyncSession, product: FixedIncomeProduct
) -> InvestFixedIncomeProductResponse:
    quote = await latest_fixed_income_quote(session, product)
    return fixed_income_response(product, quote=quote)


def fixed_income_response(
    product: FixedIncomeProduct,
    *,
    quote: FixedIncomeQuote | None = None,
) -> InvestFixedIncomeProductResponse:
    quote = quote or fixed_income_quote(product)
    cashflows = fixed_income_cashflows(product, as_of=quote.as_of)
    return InvestFixedIncomeProductResponse(
        ticker=product.ticker,
        name=product.name,
        market=product.market,
        currency=product.currency,
        issuer=product.issuer,
        instrument_type=product.instrument_type,
        tenor=product.tenor,
        maturity_date=quote.maturity_date,
        indicative_yield_pct=product.indicative_yield_pct,
        coupon_rate_pct=product.coupon_rate_pct,
        settlement_date=quote.settlement_date,
        days_to_maturity=quote.days_to_maturity,
        clean_price=quote.clean_price_per_100,
        accrued_interest=quote.accrued_interest_per_100,
        dirty_price=quote.dirty_price_per_100,
        yield_to_maturity_pct=quote.yield_to_maturity_pct,
        next_coupon_date=quote.next_coupon_date,
        face_value_increment=quote.face_value_increment,
        quote_status=quote.quote_status,
        quote_source=quote.quote_source,
        quote_provider=quote.quote_provider,
        quote_provider_label=quote.quote_provider_label,
        quote_quality=quote.quote_quality,
        quote_quality_label=quote.quote_quality_label,
        quote_type=quote.quote_type,
        quote_as_of=quote.as_of,
        quote_stale_after=quote.stale_after,
        quote_is_live=quote.quote_is_live,
        quote_stale=quote.quote_stale,
        bid_price=quote.bid_price_per_100,
        ask_price=quote.ask_price_per_100,
        mid_price=quote.mid_price_per_100,
        last_price=quote.last_price_per_100,
        bid_yield_pct=quote.bid_yield_pct,
        ask_yield_pct=quote.ask_yield_pct,
        mid_yield_pct=quote.mid_yield_pct,
        last_yield_pct=quote.last_yield_pct,
        minimum_order_amount=product.minimum_order_amount,
        liquidity=product.liquidity,
        risk_level=product.risk_level,
        expected_payout=product.expected_payout,
        trade_status=product.trade_status,
        proxy_ticker=product.proxy_ticker,
        proxy_label=product.proxy_label,
        retail_notes=list(product.retail_notes),
        pricing_assumptions=list(quote.pricing_assumptions),
        cashflows=[
            InvestFixedIncomeCashflowResponse(
                payment_date=flow.payment_date,
                cashflow_type=flow.cashflow_type,
                amount_per_100=flow.amount_per_100,
                description=flow.description,
            )
            for flow in cashflows[:8]
        ],
        risk_checks=_fixed_income_risk_checks(product, quote),
    )


def _record_from_product(
    product: FixedIncomeProduct,
) -> InvestFixedIncomeProductRecord:
    return InvestFixedIncomeProductRecord(
        ticker=product.ticker,
        name=product.name,
        market=product.market,
        currency=product.currency,
        issuer=product.issuer,
        instrument_type=product.instrument_type,
        tenor=product.tenor,
        maturity_date=(
            date.fromisoformat(product.maturity_date)
            if product.maturity_date is not None
            else None
        ),
        maturity_days=product.maturity_days,
        indicative_yield_pct=product.indicative_yield_pct,
        coupon_rate_pct=product.coupon_rate_pct,
        coupon_frequency_per_year=product.coupon_frequency_per_year,
        settlement_days=product.settlement_days,
        minimum_order_amount=product.minimum_order_amount,
        face_value_increment=product.face_value_increment,
        liquidity=product.liquidity,
        risk_level=product.risk_level,
        expected_payout=product.expected_payout,
        trade_status=product.trade_status,
        asset_class=product.asset_class,
        exchange=product.exchange,
        proxy_ticker=product.proxy_ticker,
        proxy_label=product.proxy_label,
        retail_notes=list(product.retail_notes),
        day_count_convention=product.day_count_convention,
        compounding_basis=product.compounding_basis,
        quote_source=product.quote_source,
        is_active=True,
    )


def _product_from_record(
    record: InvestFixedIncomeProductRecord,
) -> FixedIncomeProduct:
    return FixedIncomeProduct(
        ticker=record.ticker,
        name=record.name,
        market=record.market,
        currency=record.currency,
        issuer=record.issuer,
        instrument_type=record.instrument_type,
        tenor=record.tenor,
        maturity_date=(
            record.maturity_date.isoformat()
            if record.maturity_date is not None
            else None
        ),
        maturity_days=record.maturity_days,
        indicative_yield_pct=record.indicative_yield_pct,
        coupon_rate_pct=record.coupon_rate_pct,
        coupon_frequency_per_year=record.coupon_frequency_per_year,
        settlement_days=record.settlement_days,
        minimum_order_amount=record.minimum_order_amount,
        face_value_increment=record.face_value_increment,
        liquidity=record.liquidity,
        risk_level=record.risk_level,
        expected_payout=record.expected_payout,
        trade_status=record.trade_status,
        asset_class=record.asset_class,
        exchange=record.exchange,
        proxy_ticker=record.proxy_ticker,
        proxy_label=record.proxy_label,
        retail_notes=tuple(record.retail_notes or []),
        day_count_convention=record.day_count_convention,
        compounding_basis=record.compounding_basis,
        quote_source=record.quote_source,
        db_id=record.id,
    )


def _quote_record_from_quote(
    product: FixedIncomeProduct, quote: FixedIncomeQuote
) -> InvestFixedIncomeQuoteRecord:
    if product.db_id is None:
        raise ValueError("Fixed-income quote snapshots require a persisted product.")
    return InvestFixedIncomeQuoteRecord(
        product_id=product.db_id,
        yield_to_maturity_pct=quote.yield_to_maturity_pct,
        clean_price=quote.clean_price_per_100,
        accrued_interest=quote.accrued_interest_per_100,
        dirty_price=quote.dirty_price_per_100,
        settlement_date=date.fromisoformat(quote.settlement_date),
        maturity_date=date.fromisoformat(quote.maturity_date),
        days_to_maturity=quote.days_to_maturity,
        next_coupon_date=(
            date.fromisoformat(quote.next_coupon_date)
            if quote.next_coupon_date is not None
            else None
        ),
        face_value_increment=quote.face_value_increment,
        quote_status=quote.quote_status,
        quote_provider=quote.quote_provider,
        quote_quality=quote.quote_quality,
        quote_type=quote.quote_type,
        provider_security_id=quote.provider_security_id,
        bid_price=quote.bid_price_per_100,
        ask_price=quote.ask_price_per_100,
        mid_price=quote.mid_price_per_100,
        last_price=quote.last_price_per_100,
        bid_yield_pct=quote.bid_yield_pct,
        ask_yield_pct=quote.ask_yield_pct,
        mid_yield_pct=quote.mid_yield_pct,
        last_yield_pct=quote.last_yield_pct,
        source=quote.quote_source,
        source_as_of=quote.as_of,
        stale_after=quote.stale_after,
        assumptions=_assumption_payload(product, quote),
        raw_payload=quote.raw_payload,
    )


def _quote_from_record(
    product: FixedIncomeProduct,
    record: InvestFixedIncomeQuoteRecord,
    *,
    now: datetime,
) -> FixedIncomeQuote:
    stale = _aware_datetime(record.stale_after) <= now
    quote_provider = _record_text(record, "quote_provider", "internal_model")
    quote_quality = _record_text(record, "quote_quality", QUOTE_QUALITY_SEED_MODEL)
    return FixedIncomeQuote(
        as_of=_aware_datetime(record.source_as_of),
        stale_after=_aware_datetime(record.stale_after),
        settlement_date=_date_text(record.settlement_date),
        maturity_date=_date_text(record.maturity_date),
        days_to_maturity=record.days_to_maturity or 0,
        clean_price_per_100=record.clean_price or Decimal("0"),
        accrued_interest_per_100=record.accrued_interest or Decimal("0"),
        dirty_price_per_100=record.dirty_price or Decimal("0"),
        yield_to_maturity_pct=record.yield_to_maturity_pct,
        next_coupon_date=(
            _date_text(record.next_coupon_date)
            if record.next_coupon_date is not None
            else None
        ),
        face_value_increment=record.face_value_increment
        or product.face_value_increment,
        quote_status="stale_model" if stale else record.quote_status,
        quote_source=record.source,
        quote_provider=quote_provider,
        quote_provider_label=provider_label(quote_provider),
        quote_quality=quote_quality,
        quote_quality_label=quote_quality_label(quote_quality),
        quote_type=_record_text(record, "quote_type", "model"),
        quote_is_live=quote_quality_is_live(quote_quality),
        quote_stale=stale,
        provider_security_id=getattr(record, "provider_security_id", None),
        bid_price_per_100=getattr(record, "bid_price", None),
        ask_price_per_100=getattr(record, "ask_price", None),
        mid_price_per_100=getattr(record, "mid_price", None),
        last_price_per_100=getattr(record, "last_price", None),
        bid_yield_pct=getattr(record, "bid_yield_pct", None),
        ask_yield_pct=getattr(record, "ask_yield_pct", None),
        mid_yield_pct=getattr(record, "mid_yield_pct", None),
        last_yield_pct=getattr(record, "last_yield_pct", None),
        raw_payload=getattr(record, "raw_payload", None) or {},
        pricing_assumptions=_pricing_assumptions(product, record.assumptions),
    )


async def _ensure_model_yield_curves(
    session: AsyncSession, products: list[FixedIncomeProduct]
) -> None:
    today = datetime.now(timezone.utc).date()
    groups: dict[tuple[str, str], list[FixedIncomeProduct]] = {}
    for product in products:
        if product.indicative_yield_pct is None:
            continue
        groups.setdefault((product.market, product.currency), []).append(product)

    for (market, currency), grouped_products in groups.items():
        existing = await session.scalar(
            select(InvestYieldCurve).where(
                InvestYieldCurve.market == market,
                InvestYieldCurve.currency == currency,
                InvestYieldCurve.curve_date == today,
                InvestYieldCurve.source == "model_seed",
            )
        )
        if existing is not None:
            continue
        curve = InvestYieldCurve(
            market=market,
            currency=currency,
            curve_date=today,
            source="model_seed",
            metadata_={"basis": "seeded from fixed-income product yields"},
        )
        session.add(curve)
        await session.flush()
        for product in grouped_products:
            quote = fixed_income_quote(product)
            session.add(
                InvestYieldCurvePoint(
                    curve_id=curve.id,
                    tenor=product.tenor,
                    days_to_maturity=quote.days_to_maturity,
                    yield_pct=product.indicative_yield_pct,
                )
            )
    await session.flush()


def _date_text(value: date | None) -> str:
    return value.isoformat() if value is not None else ""


def _record_text(
    record: InvestFixedIncomeQuoteRecord,
    field_name: str,
    fallback: str,
) -> str:
    value = getattr(record, field_name, None)
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _assumption_payload(
    product: FixedIncomeProduct,
    quote: FixedIncomeQuote | None = None,
) -> dict:
    quote_provider = quote.quote_provider if quote is not None else "internal_model"
    quote_quality = (
        quote.quote_quality if quote is not None else QUOTE_QUALITY_SEED_MODEL
    )
    provider_plan = fixed_income_provider_plan(product)
    return {
        "day_count_convention": product.day_count_convention,
        "compounding_basis": product.compounding_basis,
        "settlement_days": product.settlement_days,
        "business_day_calendar": "Mon-Fri",
        "coupon_frequency_per_year": product.coupon_frequency_per_year,
        "source": product.quote_source,
        "quote_provider": quote_provider,
        "quote_provider_label": provider_label(quote_provider),
        "quote_quality": quote_quality,
        "quote_quality_label": quote_quality_label(quote_quality),
        "provider_plan": [
            {
                "provider": capability.provider,
                "label": capability.label,
                "source": capability.source,
                "quote_quality": capability.quote_quality,
                "status": capability.status,
            }
            for capability in provider_plan[:5]
        ],
    }


def _pricing_assumptions(
    product: FixedIncomeProduct, payload: dict | None = None
) -> tuple[str, ...]:
    assumptions = payload or _assumption_payload(product)
    quote_quality = str(
        assumptions.get("quote_quality") or QUOTE_QUALITY_SEED_MODEL
    ).strip()
    quote_provider = str(assumptions.get("quote_provider") or "internal_model").strip()
    return (
        (
            f"Quote quality: {quote_quality_label(quote_quality)} "
            f"from {provider_label(quote_provider)}."
        ),
        (
            f"Day count: {assumptions.get('day_count_convention', product.day_count_convention)}; "
            f"business days use {assumptions.get('business_day_calendar', 'Mon-Fri')}."
        ),
        f"Settlement: T+{assumptions.get('settlement_days', product.settlement_days)}.",
        (
            f"Coupon frequency: {assumptions.get('coupon_frequency_per_year', product.coupon_frequency_per_year)} "
            f"per year; compounding basis: {assumptions.get('compounding_basis', product.compounding_basis)}."
        ),
        _provider_plan_note(assumptions),
    )


def _provider_plan_note(assumptions: dict) -> str:
    provider_plan = assumptions.get("provider_plan")
    if not isinstance(provider_plan, list):
        return "Provider ladder pending; model fallback is active."
    enabled = [
        str(item.get("label"))
        for item in provider_plan
        if isinstance(item, dict) and item.get("status") == "enabled"
    ]
    planned = [
        str(item.get("label"))
        for item in provider_plan
        if isinstance(item, dict) and item.get("status") == "planned"
    ]
    if enabled:
        return f"Enabled provider path: {', '.join(enabled[:3])}."
    if planned:
        return f"Provider path prepared for: {', '.join(planned[:3])}."
    return "Provider ladder pending; model fallback is active."


def _fixed_income_risk_checks(
    product: FixedIncomeProduct, quote: FixedIncomeQuote
) -> list[InvestRiskCheckResponse]:
    return [
        InvestRiskCheckResponse(
            code="fixed_income_execution",
            level="info" if product.trade_status == "paper_tradable" else "blocker",
            message=(
                "Paper trading is enabled for this product."
                if product.trade_status == "paper_tradable"
                else "This product is watch-only."
            ),
            passed=product.trade_status == "paper_tradable",
        ),
        InvestRiskCheckResponse(
            code="quote_source",
            level="info" if quote.quote_is_live else "review",
            message=(
                f"Price uses {quote.quote_quality_label.lower()} "
                f"from {quote.quote_provider_label}."
            ),
            passed=True,
        ),
        InvestRiskCheckResponse(
            code="quote_freshness",
            level="warning" if quote.quote_stale else "info",
            message=(
                "Quote snapshot is stale; refresh before relying on the mark."
                if quote.quote_stale
                else "Quote snapshot is current."
            ),
            passed=not quote.quote_stale,
        ),
    ]


def _as_datetime(value: datetime | date | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return _aware_datetime(value)
    return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)


def _aware_datetime(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _add_business_days(start: date, days: int) -> date:
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _resolve_maturity_date(product: FixedIncomeProduct, settlement: date) -> date:
    if product.maturity_date is not None:
        return date.fromisoformat(product.maturity_date)
    if product.maturity_days is None:
        return settlement
    return settlement + timedelta(days=product.maturity_days)


def _project_cashflows(
    product: FixedIncomeProduct,
    settlement: date,
    maturity: date,
) -> list[FixedIncomeCashflow]:
    if (
        product.instrument_type == "treasury_bill"
        or product.coupon_frequency_per_year <= 0
    ):
        return [
            FixedIncomeCashflow(
                payment_date=maturity.isoformat(),
                cashflow_type="principal",
                amount_per_100=FACE_VALUE,
                description="Face value repaid at maturity.",
            )
        ]

    period_days = max(round(365 / product.coupon_frequency_per_year), 1)
    coupon = (
        (product.coupon_rate_pct or Decimal("0"))
        / Decimal(product.coupon_frequency_per_year)
    ).quantize(MONEY, rounding=ROUND_HALF_UP)
    dates: list[date] = []
    payment_date = maturity
    while payment_date > settlement:
        dates.append(payment_date)
        payment_date -= timedelta(days=period_days)
    dates.sort()

    cashflows: list[FixedIncomeCashflow] = []
    for index, payment in enumerate(dates):
        is_final = index == len(dates) - 1
        amount = coupon + (FACE_VALUE if is_final else Decimal("0"))
        cashflows.append(
            FixedIncomeCashflow(
                payment_date=payment.isoformat(),
                cashflow_type="coupon_principal" if is_final else "coupon",
                amount_per_100=amount.quantize(MONEY, rounding=ROUND_HALF_UP),
                description=(
                    "Final coupon plus face value repayment."
                    if is_final
                    else "Scheduled coupon payment."
                ),
            )
        )
    return cashflows


def _discount_bill_price(annual_yield: Decimal, days_to_maturity: int) -> Decimal:
    if days_to_maturity <= 0:
        return FACE_VALUE
    denominator = Decimal("1") + (
        annual_yield * Decimal(days_to_maturity) / Decimal("365")
    )
    if denominator <= 0:
        return FACE_VALUE
    return FACE_VALUE / denominator


def _coupon_bond_dirty_price(
    product: FixedIncomeProduct,
    annual_yield: Decimal,
    cashflows: list[FixedIncomeCashflow],
) -> Decimal:
    if not cashflows:
        return FACE_VALUE
    frequency = max(product.coupon_frequency_per_year, 1)
    periodic_yield = Decimal("1") + (annual_yield / Decimal(frequency))
    price = Decimal("0")
    for index, flow in enumerate(cashflows, start=1):
        price += flow.amount_per_100 / (periodic_yield**index)
    return price


def _accrued_interest(
    product: FixedIncomeProduct,
    settlement: date,
    maturity: date,
) -> Decimal:
    if not product.coupon_rate_pct or product.coupon_frequency_per_year <= 0:
        return Decimal("0")
    period_days = max(round(365 / product.coupon_frequency_per_year), 1)
    coupon = product.coupon_rate_pct / Decimal(product.coupon_frequency_per_year)
    next_coupon = maturity
    while next_coupon - timedelta(days=period_days) > settlement:
        next_coupon -= timedelta(days=period_days)
    previous_coupon = next_coupon - timedelta(days=period_days)
    elapsed_days = max((settlement - previous_coupon).days, 0)
    total_days = max((next_coupon - previous_coupon).days, 1)
    return coupon * Decimal(elapsed_days) / Decimal(total_days)


def _price(value: Decimal) -> Decimal:
    return value.quantize(PRICE, rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _is_missing_fixed_income_table(exc: Exception) -> bool:
    message = str(exc).lower()
    table_names = (
        "invest_fixed_income_products",
        "invest_fixed_income_quotes",
        "invest_yield_curves",
        "invest_yield_curve_points",
    )
    return any(table_name in message for table_name in table_names) and (
        "does not exist" in message
        or "undefinedtable" in message
        or "undefinedcolumn" in message
        or "no such column" in message
        or "no such table" in message
    )


async def _rollback_after_fixed_income_fallback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:
        logger.exception("fixed_income_fallback_rollback_failed")


async def _fixed_income_table_exists(session: AsyncSession, table_name: str) -> bool:
    connection = await session.connection()
    return await connection.run_sync(
        lambda sync_connection: sqlalchemy_inspect(sync_connection).has_table(
            table_name
        )
    )
