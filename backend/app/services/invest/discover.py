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
from app.services.invest.accounts import list_watchlist
from app.services.invest.fixed_income import search_fixed_income_products
from app.services.market_radar.overview import build_radar_overview
from app.services.news.centre import build_news_overview


async def build_invest_discover(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> InvestDiscoverResponse:
    generated_at = datetime.now(timezone.utc)
    radar = await build_radar_overview(session, jurisdiction="all", owner_user_id=user.id)
    news = await build_news_overview(
        session,
        jurisdiction="all",
        page=1,
        page_size=10,
        owner_user_id=user.id,
    )
    watchlist = await list_watchlist(session, user)

    sections = [
        _market_pulse_section(radar),
        _fixed_income_section(),
        _watchlist_section(watchlist),
        _news_section(news),
    ]

    summary = _summary(radar.flagged_count, len(news.current), len(watchlist))

    return InvestDiscoverResponse(
        generated_at=generated_at,
        summary=summary,
        sections=sections,
        next_actions=_next_actions(has_watchlist=bool(watchlist)),
    )


def _summary(flagged_count: int, news_count: int, watchlist_count: int) -> str:
    if flagged_count > 0:
        return (
            f"{flagged_count} market moves need a closer look. "
            f"Your watchlist has {watchlist_count} saved names, and {news_count} current stories are available."
        )
    return (
        "Start with fixed income, broad market context, and your watchlist. "
        f"{news_count} current stories are available for review."
    )


def _market_pulse_section(radar) -> InvestDiscoverSectionResponse:
    items: list[InvestDiscoverItemResponse] = []
    for item in radar.flagged[:5]:
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
                title="No urgent equity moves right now",
                subtitle="Radar has not found a high-priority retail move in the latest working set.",
                badge="Quiet",
                href="/invest/search",
                metadata=[f"{radar.working_set_count} names screened"],
            )
        )

    return InvestDiscoverSectionResponse(
        id="market_pulse",
        title="Market pulse",
        description="Plain-language highlights from the shared Market Radar.",
        items=items,
    )


def _fixed_income_section() -> InvestDiscoverSectionResponse:
    products = search_fixed_income_products()
    items = [
        InvestDiscoverItemResponse(
            title=product.name,
            subtitle=product.expected_payout,
            badge=product.trade_status.replace("_", " "),
            href=f"/invest/fixed-income/{product.ticker}",
            tone="income",
            metadata=[
                product.currency,
                product.issuer,
                f"Minimum {product.currency} {product.minimum_order_amount}",
                product.liquidity,
            ],
        )
        for product in products[:4]
    ]
    return InvestDiscoverSectionResponse(
        id="fixed_income",
        title="Fixed income shelf",
        description="Bills and bonds to understand before fixed-income execution is enabled.",
        items=items,
    )


def _watchlist_section(watchlist) -> InvestDiscoverSectionResponse:
    items: list[InvestDiscoverItemResponse] = []
    for item in watchlist[:5]:
        items.append(
            InvestDiscoverItemResponse(
                title=f"{item.ticker} - {item.name}",
                subtitle=item.notes or "Saved for follow-up.",
                badge="Watchlist",
                href=f"/invest/instruments/{item.ticker}",
                tone="watchlist",
                metadata=[_money(item.price) if item.price is not None else "No live mark"],
            )
        )

    if not items:
        items.append(
            InvestDiscoverItemResponse(
                title="Build your first watchlist",
                subtitle="Save stocks, ETFs, and later fixed-income products you want to track.",
                badge="Start",
                href="/invest/search",
                metadata=["Search AAPL, SPY, or a Treasury product"],
            )
        )

    return InvestDiscoverSectionResponse(
        id="watchlist",
        title="Your watchlist",
        description="Names you saved, with a quick prompt for what to review next.",
        items=items,
    )


def _news_section(news) -> InvestDiscoverSectionResponse:
    source_items = news.watchlist_items[:3] or news.current[:4]
    items = [
        InvestDiscoverItemResponse(
            title=item.title,
            subtitle=item.summary,
            badge=item.source_name or item.jurisdiction or "News",
            href=item.url,
            tone="news",
            metadata=[
                *(item.tickers[:3] if item.tickers else []),
                item.sentiment_label or "",
            ],
        )
        for item in source_items
    ]
    if not items:
        items.append(
            InvestDiscoverItemResponse(
                title="No current news loaded",
                subtitle="Run the News Centre poll to refresh retail market stories.",
                badge="News",
                href="/news",
                metadata=[],
            )
        )
    return InvestDiscoverSectionResponse(
        id="news",
        title="News to read",
        description="Current and watchlist-linked stories, without Capital-only interpretation.",
        items=items,
    )


def _next_actions(has_watchlist: bool) -> list[InvestDiscoverItemResponse]:
    actions = [
        InvestDiscoverItemResponse(
            title="Compare cash yield products",
            subtitle="Review T-bills, Treasury notes, and FGN bonds before they become tradable.",
            badge="Fixed income",
            href="/invest/markets",
            tone="income",
        ),
        InvestDiscoverItemResponse(
            title="Search a security",
            subtitle="Open a retail asset detail page and decide whether it belongs on your watchlist.",
            badge="Research",
            href="/invest/search",
            tone="neutral",
        ),
    ]
    if has_watchlist:
        actions.append(
            InvestDiscoverItemResponse(
                title="Review saved names",
                subtitle="Check prices, news, and any unusual movement in your watchlist.",
                badge="Watchlist",
                href="/invest/watchlist",
                tone="watchlist",
            )
        )
    return actions


def _plain_radar_reason(item) -> str:
    if item.priority_reasons:
        return item.priority_reasons[0]
    if item.flags:
        return f"{item.ticker} is moving differently from its recent pattern."
    return f"{item.ticker} appeared in the latest radar working set."


def _pct(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:+.2f}%"


def _ratio(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:.1f}x volume"


def _money(value: Decimal | None) -> str:
    if value is None:
        return "No live mark"
    return f"${value:.2f}"


def _tone_for_change(value: Decimal | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"
