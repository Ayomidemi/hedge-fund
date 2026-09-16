from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.invest import (
    InvestDiscoverItemResponse,
    InvestDiscoverResponse,
    InvestDiscoverSectionResponse,
)
from app.core.auth import AuthenticatedUser
from app.services.invest.fixed_income import (
    fixed_income_quote,
    search_fixed_income_products,
)
from app.services.market_radar.overview import build_radar_overview


async def build_invest_discover(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> InvestDiscoverResponse:
    generated_at = datetime.now(timezone.utc)
    radar = await build_radar_overview(
        session, jurisdiction="all", owner_user_id=user.id
    )

    sections = [
        _fixed_income_section(),
        _market_context_section(radar),
    ]

    return InvestDiscoverResponse(
        generated_at=generated_at,
        summary=_summary(radar.flagged_count, radar.working_set_count),
        sections=sections,
        next_actions=_next_actions(),
    )


def _summary(flagged_count: int, working_set_count: int) -> str:
    if flagged_count > 0:
        return (
            "Start with modeled fixed-income yield, then use market context to decide "
            f"what deserves attention. {flagged_count} unusual moves are available."
        )
    return (
        f"Start with fixed income and broad market context. The latest scan covered {working_set_count} names."
    )


def _market_context_section(radar) -> InvestDiscoverSectionResponse:
    items: list[InvestDiscoverItemResponse] = []
    for item in radar.flagged[:8]:
        move = _pct(item.change_pct)
        volume = _ratio(item.volume_ratio)
        bits = [bit for bit in [move, volume, item.industry or item.sector] if bit]
        items.append(
            InvestDiscoverItemResponse(
                title=f"{item.ticker} - {item.name}",
                subtitle=_plain_radar_reason(item),
                badge=item.radar_priority or "Move",
                href=f"/invest/instruments/{item.ticker}",
                tone=_tone_for_change(item.change_pct),
                metadata=bits,
            )
        )

    if not items:
        items.append(
            InvestDiscoverItemResponse(
                title="No unusual moves right now",
                subtitle="The latest scan did not flag a high-priority name.",
                badge="Quiet",
                href="/invest/markets",
                metadata=[f"{radar.working_set_count} names screened"],
            )
        )

    return InvestDiscoverSectionResponse(
        id="market_context",
        title="Market context",
        description="Plain-language movement after the fixed-income shelf.",
        items=items,
    )


def _fixed_income_section() -> InvestDiscoverSectionResponse:
    products = search_fixed_income_products()
    items = []
    for product in products[:4]:
        quote = fixed_income_quote(product)
        items.append(
            InvestDiscoverItemResponse(
                title=product.name,
                subtitle=product.expected_payout,
                badge=product.trade_status.replace("_", " "),
                href=f"/invest/fixed-income/{product.ticker}",
                tone="income",
                metadata=[
                    product.currency,
                    f"YTM {quote.yield_to_maturity_pct}%",
                    f"Dirty {quote.dirty_price_per_100}/100",
                    f"Matures {quote.maturity_date}",
                    f"Minimum {product.currency} {product.minimum_order_amount}",
                ],
            )
        )
    return InvestDiscoverSectionResponse(
        id="fixed_income",
        title="Fixed income shelf",
        description="Bills and bonds with modeled yield, settlement, price, and payout context.",
        items=items,
    )


def _next_actions() -> list[InvestDiscoverItemResponse]:
    return [
        InvestDiscoverItemResponse(
            title="Compare fixed-income products",
            subtitle="Review modeled yield, settlement, and payout before placing a paper order.",
            badge="Fixed income",
            href="/invest/markets",
            tone="income",
        ),
        InvestDiscoverItemResponse(
            title="Search an instrument",
            subtitle="Look up funds and listed instruments after reviewing cash-yield products.",
            badge="Research",
            href="/invest/search",
            tone="neutral",
        ),
    ]


def _plain_radar_reason(item) -> str:
    if item.priority_reasons:
        return item.priority_reasons[0]
    if item.flags:
        return f"{item.ticker} is moving differently from its recent pattern."
    return f"{item.ticker} appeared in the secondary market scan."


def _pct(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:+.2f}%"


def _ratio(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:.1f}x volume"


def _tone_for_change(value: Decimal | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"
