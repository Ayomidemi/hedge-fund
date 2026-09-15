from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.invest import InvestFixedIncomeProductResponse
from app.api.schemas.operating_core import InstrumentCreate
from app.models import Instrument
from app.services.portfolio.operating_core import upsert_instrument


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
    indicative_yield_pct: Decimal | None
    minimum_order_amount: Decimal
    liquidity: str
    risk_level: str
    expected_payout: str
    trade_status: str
    asset_class: str
    exchange: str | None
    retail_notes: tuple[str, ...]


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
        indicative_yield_pct=None,
        minimum_order_amount=Decimal("100.00"),
        liquidity="Very high",
        risk_level="Low",
        expected_payout="Discount bill; return is earned between purchase price and face value at maturity.",
        trade_status="watch_only",
        asset_class="cash_equivalent",
        exchange="TREASURY",
        retail_notes=(
            "Paper trading can model the position, but live T-bill execution needs a fixed-income broker adapter.",
            "Yield changes before maturity can affect resale value.",
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
        indicative_yield_pct=None,
        minimum_order_amount=Decimal("100.00"),
        liquidity="Very high",
        risk_level="Low",
        expected_payout="Semiannual coupons plus principal repayment at maturity.",
        trade_status="watch_only",
        asset_class="bond",
        exchange="TREASURY",
        retail_notes=(
            "Principal is backed by the US Treasury when held to maturity.",
            "Market value can fall if rates rise.",
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
        indicative_yield_pct=None,
        minimum_order_amount=Decimal("100000.00"),
        liquidity="Medium",
        risk_level="Medium",
        expected_payout="Discount bill; return is earned between purchase price and face value at maturity.",
        trade_status="watch_only",
        asset_class="cash_equivalent",
        exchange="FMDQ",
        retail_notes=(
            "Execution requires a Nigeria fixed-income broker or bank partner.",
            "NGN inflation and currency risk matter for USD-based investors.",
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
        maturity_date=None,
        indicative_yield_pct=None,
        minimum_order_amount=Decimal("100000.00"),
        liquidity="Medium",
        risk_level="Medium",
        expected_payout="Periodic coupons plus principal repayment at maturity.",
        trade_status="watch_only",
        asset_class="bond",
        exchange="FMDQ",
        retail_notes=(
            "Coupon, clean price, accrued interest, and settlement rules must be modeled before live orders.",
            "Secondary-market liquidity can vary by issue.",
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


def fixed_income_response(product: FixedIncomeProduct) -> InvestFixedIncomeProductResponse:
    return InvestFixedIncomeProductResponse(
        ticker=product.ticker,
        name=product.name,
        market=product.market,
        currency=product.currency,
        issuer=product.issuer,
        instrument_type=product.instrument_type,
        tenor=product.tenor,
        maturity_date=product.maturity_date,
        indicative_yield_pct=product.indicative_yield_pct,
        minimum_order_amount=product.minimum_order_amount,
        liquidity=product.liquidity,
        risk_level=product.risk_level,
        expected_payout=product.expected_payout,
        trade_status=product.trade_status,
        retail_notes=list(product.retail_notes),
    )
