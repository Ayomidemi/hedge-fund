from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.invest import (
    InvestDiscoverItemResponse,
    InvestDiscoverResponse,
    InvestDiscoverSectionResponse,
)
from app.core.auth import AuthenticatedUser
from app.core.market_constants import RADAR_PULSE_TICKERS
from app.models import RadarRun, RadarSnapshot, RetailWatchlistItem
from app.services.invest.markets import active_board_tickers
from app.services.invest.news import (
    income_news_items,
    is_income_story,
    latest_news_items,
)
from app.services.market_radar.overview import build_radar_overview

UNUSUAL_LIMIT = 10
SECTOR_LIMIT = 6
WATCHLIST_LIMIT = 8
BOARD_LIMIT = 6

_DESK_WORDS = (
    "radar",
    "p0",
    "p1",
    "p2",
    "p3",
    "queue",
    "ticker analyst",
    "auto-open",
    "auto-promote",
    "working set",
)


async def build_invest_discover(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> InvestDiscoverResponse:
    generated_at = datetime.now(timezone.utc)
    radar = await build_radar_overview(session, jurisdiction="all")
    watchlist_tickers = await _retail_watchlist_tickers(session, user.id)
    board = {ticker.upper() for ticker in await active_board_tickers(session)}
    flagged = list(radar.flagged)
    unusual = [
        item
        for item in flagged
        if item.ticker.upper() not in RADAR_PULSE_TICKERS
    ]
    unusual.sort(key=_retail_sort_key)
    watchlist_moves = [
        item for item in flagged if item.ticker.upper() in watchlist_tickers
    ]
    watchlist_moves.sort(key=_retail_sort_key)
    board_moves = [item for item in flagged if item.ticker.upper() in board]
    board_moves.sort(key=_retail_sort_key)
    news_section = await _news_section(session)
    narrative = _narrative(radar.industries, unusual)

    sections = [
        _unusual_section(unusual, screened=radar.working_set_count),
        _sector_section(radar.industries),
        news_section,
        _watchlist_section(watchlist_moves, watchlist_tickers),
        _board_section(board_moves),
    ]

    return InvestDiscoverResponse(
        generated_at=generated_at,
        summary=_summary(
            unusual_count=len(unusual),
            sector_count=_active_industry_count(radar.industries),
            watchlist_hits=len(watchlist_moves),
            watchlist_count=len(watchlist_tickers),
        ),
        narrative=narrative,
        sections=sections,
        next_actions=_next_actions(watchlist_tickers),
    )


def _unusual_section(
    items, *, screened: int
) -> InvestDiscoverSectionResponse:
    cards = [_name_card(item) for item in items[:UNUSUAL_LIMIT]]
    if not cards:
        cards.append(
            InvestDiscoverItemResponse(
                title="Markets look quiet",
                subtitle="The latest scan did not flag a name moving far from its recent pattern.",
                badge="Quiet",
                href="/invest/markets",
                metadata=[f"{screened} names screened"] if screened else [],
            )
        )
    return InvestDiscoverSectionResponse(
        id="unusual_activity",
        title="Unusual activity",
        description="Names moving differently from their recent pattern — not a recommendation.",
        items=cards,
    )


def _sector_section(industries) -> InvestDiscoverSectionResponse:
    cards: list[InvestDiscoverItemResponse] = []
    for industry in industries:
        if industry.status not in {"industry_event", "market_event"}:
            continue
        cards.append(_industry_card(industry))
        if len(cards) >= SECTOR_LIMIT:
            break
    if not cards:
        cards.append(
            InvestDiscoverItemResponse(
                title="No group move stands out",
                subtitle="Sectors are not moving together in an unusual way right now.",
                badge="Quiet",
                href="/invest/markets",
            )
        )
    return InvestDiscoverSectionResponse(
        id="sector_moves",
        title="Sector moves",
        description="Where a group of related names is active at the same time.",
        items=cards,
    )


def _watchlist_section(
    items, watchlist_tickers: set[str]
) -> InvestDiscoverSectionResponse:
    if not watchlist_tickers:
        cards = [
            InvestDiscoverItemResponse(
                title="Watchlist is empty",
                subtitle="Add names you care about. Unusual moves in those names will show up here.",
                badge="Watchlist",
                href="/invest/watchlist",
            )
        ]
    elif not items:
        cards = [
            InvestDiscoverItemResponse(
                title="Your names look steady",
                subtitle="None of your watchlist tickers were unusual in the latest scan.",
                badge="Quiet",
                href="/invest/watchlist",
                metadata=[f"{len(watchlist_tickers)} watched"],
            )
        ]
    else:
        cards = [_name_card(item, kind="Watch") for item in items[:WATCHLIST_LIMIT]]
    return InvestDiscoverSectionResponse(
        id="watchlist_updates",
        title="Watchlist updates",
        description="Unusual tape in names you already track on Pease Invest.",
        items=cards,
    )


def _board_section(items) -> InvestDiscoverSectionResponse:
    cards = [_name_card(item, kind="Board") for item in items[:BOARD_LIMIT]]
    if not cards:
        cards.append(
            InvestDiscoverItemResponse(
                title="Board tape is calm",
                subtitle="Index funds and listed proxies on the Invest board are not making unusual prints.",
                badge="Quiet",
                href="/invest/markets",
            )
        )
    return InvestDiscoverSectionResponse(
        id="board_movers",
        title="On the boards",
        description="Unusual prints among the listed names on the Invest markets board.",
        items=cards,
    )


async def _news_section(session: AsyncSession) -> InvestDiscoverSectionResponse:
    income = await income_news_items(session, limit=3)
    latest = await latest_news_items(session, limit=8)
    cards: list[InvestDiscoverItemResponse] = []
    seen: set = set()
    for item in [*income, *latest]:
        if item.id in seen:
            continue
        seen.add(item.id)
        tickers = [link.ticker for link in (item.ticker_links or [])]
        rates = is_income_story(
            title=item.title,
            summary=item.summary,
            tickers=tickers,
        )
        lead = next((ticker for ticker in tickers if ticker), None)
        cards.append(
            InvestDiscoverItemResponse(
                title=item.title,
                subtitle=item.source_name or item.provider,
                badge="Rates" if rates else "Headline",
                href=(
                    f"/invest/news?ticker={lead}"
                    if lead
                    else "/invest/news"
                ),
                tone="income" if rates else "neutral",
                metadata=tickers[:3],
            )
        )
        if len(cards) >= 5:
            break
    if not cards:
        cards.append(
            InvestDiscoverItemResponse(
                title="No stored headlines yet",
                subtitle="Rates and listed tape land on News when Tiingo has copy.",
                badge="News",
                href="/invest/news",
            )
        )
    return InvestDiscoverSectionResponse(
        id="latest_news",
        title="Latest headlines",
        description="Rates first when the tape has Treasury, bill, or FGN copy. Full article list stays on News.",
        items=cards,
    )


def _narrative(industries, unusual) -> str | None:
    for industry in industries:
        if industry.status in {"industry_event", "market_event"}:
            return _sector_copy(industry)
    if unusual:
        return _move_copy(unusual[0])
    return None


async def home_tape_headline(session: AsyncSession) -> str | None:
    run_id = await session.scalar(
        select(RadarRun.id)
        .where(RadarRun.status == "completed")
        .where(RadarRun.working_set_count > 0)
        .order_by(RadarRun.started_at.desc())
        .limit(1)
    )
    if run_id is None:
        return None
    snapshots = list(
        await session.scalars(
            select(RadarSnapshot)
            .where(RadarSnapshot.run_id == run_id)
            .where(RadarSnapshot.in_working_set.is_(True))
            .where(func.jsonb_array_length(RadarSnapshot.flags) > 0)
            .order_by(RadarSnapshot.anomaly_score.desc())
            .limit(12)
        )
    )
    unusual = [
        item
        for item in snapshots
        if item.ticker.upper() not in RADAR_PULSE_TICKERS
    ]
    unusual.sort(key=_retail_sort_key)
    if not unusual:
        return None
    return _move_copy(unusual[0])


def _next_actions(watchlist_tickers: set[str]) -> list[InvestDiscoverItemResponse]:
    if watchlist_tickers:
        return []
    return [
        InvestDiscoverItemResponse(
            title="Build a watchlist",
            subtitle="Personalize unusual activity with the names you actually follow.",
            badge="Watchlist",
            href="/invest/watchlist",
        ),
        InvestDiscoverItemResponse(
            title="Read headlines",
            subtitle="Article tape lives on News, not on this page.",
            badge="News",
            href="/invest/news",
        ),
    ]


def _name_card(item, *, kind: str | None = None) -> InvestDiscoverItemResponse:
    bits = [bit for bit in [_pct(item.change_pct), _ratio(item.volume_ratio)] if bit]
    group = item.industry or item.sector
    if group:
        bits.append(group)
    if kind:
        bits.append(kind)
    return InvestDiscoverItemResponse(
        title=f"{item.ticker} — {item.name}",
        subtitle=_move_copy(item),
        badge=_retail_badge(item),
        href=f"/invest/instruments/{item.ticker}",
        tone=_tone_for_change(item.change_pct),
        metadata=bits,
    )


def _industry_card(industry) -> InvestDiscoverItemResponse:
    lead = next((name for name in industry.names if name.flags), None)
    href = (
        f"/invest/instruments/{lead.ticker}"
        if lead is not None
        else "/invest/markets"
    )
    tickers = [name.ticker for name in industry.names if name.flags][:4]
    metadata = [
        bit
        for bit in [
            _pct(industry.median_change_pct),
            f"{industry.flagged_count} of {industry.name_count} moving",
            *tickers,
        ]
        if bit
    ]
    return InvestDiscoverItemResponse(
        title=industry.name,
        subtitle=_sector_copy(industry),
        badge=_sector_badge(industry),
        href=href,
        tone=_tone_for_change(industry.median_change_pct),
        metadata=metadata,
    )


def _move_copy(item) -> str:
    ticker = item.ticker
    move = _plain_pct(item.change_pct)
    volume = _ratio(item.volume_ratio)
    group = item.industry or item.sector
    if item.change_pct is not None and move:
        direction = "up" if item.change_pct > 0 else "down"
        sentence = f"{ticker} is {direction} {move}"
    else:
        sentence = f"{ticker} is moving differently from its recent pattern"
    if volume:
        sentence = f"{sentence} on {volume}"
    if group:
        sentence = f"{sentence} in {group.lower()}"
    return f"{sentence}."


def _sector_copy(industry) -> str:
    label = industry.name
    flagged = industry.flagged_count
    members = industry.name_count
    move = _plain_pct(industry.median_change_pct)
    if industry.status == "market_event":
        market = "US" if industry.jurisdiction == "US" else "Nigerian"
        if move:
            return f"The broader {market} tape is moving together, about {move} across groups."
        return f"The broader {market} tape is moving together today."
    if move:
        return (
            f"{label} names are unusually active — {flagged} of {members} "
            f"moved, around {move}."
        )
    return f"{label} names are unusually active — {flagged} of {members} moved together."


def _retail_badge(item) -> str:
    flags = {str(flag) for flag in (item.flags or [])}
    if "unusual_volume" in flags or "volume_anomaly" in flags:
        return "Heavy volume"
    if "scan_lurch" in flags or "price_anomaly" in flags:
        return "Unusual"
    if "risk_drop" in flags:
        return "Down"
    if item.change_pct is not None and item.change_pct > 0:
        return "Up"
    if item.change_pct is not None and item.change_pct < 0:
        return "Down"
    return "Move"


def _sector_badge(industry) -> str:
    if industry.status == "market_event":
        return "Broad tape"
    if industry.median_change_pct is not None and industry.median_change_pct > 0:
        return "Strong"
    if industry.median_change_pct is not None and industry.median_change_pct < 0:
        return "Soft"
    return "Active"


def _summary(
    *,
    unusual_count: int,
    sector_count: int,
    watchlist_hits: int,
    watchlist_count: int,
) -> str:
    if unusual_count == 0 and sector_count == 0:
        if watchlist_count:
            return (
                "Markets look quiet. None of the latest unusual prints hit your watchlist."
            )
        return (
            "Markets look quiet. Add watchlist names to see when something you follow moves."
        )
    parts: list[str] = []
    if unusual_count:
        parts.append(
            f"{unusual_count} unusual name{'s' if unusual_count != 1 else ''}"
        )
    if sector_count:
        parts.append(
            f"{sector_count} group move{'s' if sector_count != 1 else ''}"
        )
    headline = " and ".join(parts)
    if watchlist_hits:
        return (
            f"{headline.capitalize()} in the latest scan. "
            f"{watchlist_hits} of your watched names are in that tape."
        )
    if watchlist_count:
        return f"{headline.capitalize()} in the latest scan. Your watchlist is quiet."
    return (
        f"{headline.capitalize()} in the latest scan. "
        "This is market context, not a recommendation."
    )


def _retail_sort_key(item) -> tuple:
    change = abs(item.change_pct or Decimal("0"))
    volume = item.volume_ratio or Decimal("0")
    return (-change, -volume, item.ticker)


def _active_industry_count(industries) -> int:
    return sum(
        1
        for industry in industries
        if industry.status in {"industry_event", "market_event"}
    )


async def _retail_watchlist_tickers(
    session: AsyncSession, user_id: str
) -> set[str]:
    rows = await session.scalars(
        select(RetailWatchlistItem)
        .options(selectinload(RetailWatchlistItem.instrument))
        .where(RetailWatchlistItem.user_id == user_id)
    )
    tickers: set[str] = set()
    for row in rows:
        ticker = (row.instrument.ticker if row.instrument is not None else "").upper()
        if ticker:
            tickers.add(ticker)
    return tickers


def _pct(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:+.2f}%"


def _plain_pct(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{abs(value):.2f}%"


def _ratio(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:.1f}× volume"


def _tone_for_change(value: Decimal | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def uses_desk_language(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _DESK_WORDS)
