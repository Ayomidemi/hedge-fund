from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.invest import (
    InvestFixedIncomeCashflowResponse,
    InvestFixedIncomeProductResponse,
)
from app.api.schemas.operating_core import InstrumentCreate
from app.models import Instrument
from app.services.portfolio.operating_core import upsert_instrument

PRICE = Decimal("0.0001")
MONEY = Decimal("0.01")
FACE_VALUE = Decimal("100")


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


@dataclass(frozen=True)
class FixedIncomeCashflow:
    payment_date: str
    cashflow_type: str
    amount_per_100: Decimal
    description: str


@dataclass(frozen=True)
class FixedIncomeQuote:
    as_of: datetime
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


FIXED_INCOME_PRODUCTS: tuple[FixedIncomeProduct, ...] = (
    FixedIncomeProduct(
        ticker="US-TBILL-13W",
        name="US Treasury Bill 13 Week",
        market="US",
        currency="USD",
        issuer="United States Treasury",
        instrument_type="treasury_bill",
        tenor="13 weeks",
        maturity_date=None,
        maturity_days=91,
        indicative_yield_pct=Decimal("4.85"),
        coupon_rate_pct=Decimal("0"),
        coupon_frequency_per_year=0,
        settlement_days=1,
        minimum_order_amount=Decimal("100.00"),
        face_value_increment=Decimal("100.00"),
        liquidity="Very high",
        risk_level="Low",
        expected_payout="Discount bill; return is earned between purchase price and face value at maturity.",
        trade_status="paper_tradable",
        asset_class="cash_equivalent",
        exchange="TREASURY",
        proxy_ticker="BIL",
        proxy_label="Paper the T-bill move with BIL",
        retail_notes=(
            "Paper fills use an indicative discount-bill model, not a live Treasury auction feed.",
            "BIL remains available as a listed proxy when you want exchange-traded exposure.",
        ),
    ),
    FixedIncomeProduct(
        ticker="US-TREASURY-2Y",
        name="US Treasury Note 2 Year",
        market="US",
        currency="USD",
        issuer="United States Treasury",
        instrument_type="treasury_note",
        tenor="2 years",
        maturity_date=None,
        maturity_days=730,
        indicative_yield_pct=Decimal("4.10"),
        coupon_rate_pct=Decimal("4.00"),
        coupon_frequency_per_year=2,
        settlement_days=1,
        minimum_order_amount=Decimal("100.00"),
        face_value_increment=Decimal("100.00"),
        liquidity="Very high",
        risk_level="Low",
        expected_payout="Semiannual coupons plus principal repayment at maturity.",
        trade_status="paper_tradable",
        asset_class="bond",
        exchange="TREASURY",
        proxy_ticker="SHY",
        proxy_label="Paper short-duration Treasuries with SHY",
        retail_notes=(
            "Paper fills track clean price, accrued interest, settlement, and projected coupon dates.",
            "SHY remains available as a listed proxy for ETF-style short-duration exposure.",
        ),
    ),
    FixedIncomeProduct(
        ticker="NG-TBILL-182D",
        name="Nigeria Treasury Bill 182 Day",
        market="NG",
        currency="NGN",
        issuer="Federal Government of Nigeria",
        instrument_type="treasury_bill",
        tenor="182 days",
        maturity_date=None,
        maturity_days=182,
        indicative_yield_pct=Decimal("18.50"),
        coupon_rate_pct=Decimal("0"),
        coupon_frequency_per_year=0,
        settlement_days=2,
        minimum_order_amount=Decimal("100000.00"),
        face_value_increment=Decimal("1000.00"),
        liquidity="Medium",
        risk_level="Medium",
        expected_payout="Discount bill; return is earned between purchase price and face value at maturity.",
        trade_status="paper_tradable",
        asset_class="cash_equivalent",
        exchange="FMDQ",
        proxy_ticker=None,
        proxy_label=None,
        retail_notes=(
            "Paper fills use an indicative Nigerian T-bill discount model with T+2 settlement.",
            "There is no honest listed ETF proxy for Nigerian T-bills on this board yet.",
        ),
    ),
    FixedIncomeProduct(
        ticker="FGN-BOND-2029",
        name="FGN Bond 2029",
        market="NG",
        currency="NGN",
        issuer="Federal Government of Nigeria",
        instrument_type="government_bond",
        tenor="Medium term",
        maturity_date="2029-04-27",
        maturity_days=None,
        indicative_yield_pct=Decimal("19.75"),
        coupon_rate_pct=Decimal("16.25"),
        coupon_frequency_per_year=2,
        settlement_days=2,
        minimum_order_amount=Decimal("100000.00"),
        face_value_increment=Decimal("1000.00"),
        liquidity="Medium",
        risk_level="Medium",
        expected_payout="Periodic coupons plus principal repayment at maturity.",
        trade_status="paper_tradable",
        asset_class="bond",
        exchange="FMDQ",
        proxy_ticker=None,
        proxy_label=None,
        retail_notes=(
            "Paper fills model clean price, accrued interest, coupons, and principal repayment.",
            "There is no honest listed ETF proxy for FGN bonds on this board yet.",
        ),
    ),
)


def get_fixed_income_product(ticker: str) -> FixedIncomeProduct | None:
    normalized = ticker.strip().upper()
    for product in FIXED_INCOME_PRODUCTS:
        if product.ticker == normalized:
            return product
    return None


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

    return FixedIncomeQuote(
        as_of=quote_as_of,
        settlement_date=settlement.isoformat(),
        maturity_date=maturity.isoformat(),
        days_to_maturity=days_to_maturity,
        clean_price_per_100=_price(clean_price),
        accrued_interest_per_100=_price(accrued_interest),
        dirty_price_per_100=_price(dirty_price),
        yield_to_maturity_pct=(
            _percent(product.indicative_yield_pct)
            if product.indicative_yield_pct is not None
            else None
        ),
        next_coupon_date=next_coupon_date,
        face_value_increment=product.face_value_increment,
        quote_status="indicative_model",
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


def fixed_income_response(product: FixedIncomeProduct) -> InvestFixedIncomeProductResponse:
    quote = fixed_income_quote(product)
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
        minimum_order_amount=product.minimum_order_amount,
        liquidity=product.liquidity,
        risk_level=product.risk_level,
        expected_payout=product.expected_payout,
        trade_status=product.trade_status,
        proxy_ticker=product.proxy_ticker,
        proxy_label=product.proxy_label,
        retail_notes=list(product.retail_notes),
        cashflows=[
            InvestFixedIncomeCashflowResponse(
                payment_date=flow.payment_date,
                cashflow_type=flow.cashflow_type,
                amount_per_100=flow.amount_per_100,
                description=flow.description,
            )
            for flow in cashflows[:8]
        ],
    )


def _as_datetime(value: datetime | date | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)


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
    if product.instrument_type == "treasury_bill" or product.coupon_frequency_per_year <= 0:
        return [
            FixedIncomeCashflow(
                payment_date=maturity.isoformat(),
                cashflow_type="principal",
                amount_per_100=FACE_VALUE,
                description="Face value repaid at maturity.",
            )
        ]

    period_days = max(round(365 / product.coupon_frequency_per_year), 1)
    coupon = ((product.coupon_rate_pct or Decimal("0")) / Decimal(product.coupon_frequency_per_year)).quantize(
        MONEY, rounding=ROUND_HALF_UP
    )
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
        price += flow.amount_per_100 / (periodic_yield ** index)
    return price


def _accrued_interest(
    product: FixedIncomeProduct,
    settlement: date,
    maturity: date,
) -> Decimal:
    if not product.coupon_rate_pct or product.coupon_frequency_per_year <= 0:
        return Decimal("0")
    period_days = max(round(365 / product.coupon_frequency_per_year), 1)
    coupon = (product.coupon_rate_pct / Decimal(product.coupon_frequency_per_year))
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
