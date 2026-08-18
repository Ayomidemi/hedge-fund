from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.news import (
    NewsItemResponse,
    NewsOverviewResponse,
    NewsPollRunResponse,
)
from app.core.config import settings
from app.models import (
    Instrument,
    NewsItem,
    NewsPollRun,
    NewsTickerLink,
    RadarRun,
    RadarWatchlistItem,
)
from app.services.market_data.sessions import jurisdiction_for_ticker
from app.services.market_radar.watchlist import load_always_watched
from app.services.news.providers import (
    ProviderNewsItem,
    fetch_current_news,
    fetch_news_for_ticker,
    normalize_ticker,
)

logger = logging.getLogger(__name__)

CURRENT_NEWS_LIMIT = 80
TICKER_NEWS_LIMIT = 60
WATCHLIST_NEWS_LIMIT = 50


class NewsUnavailableError(RuntimeError):
    pass


async def poll_news(
    session: AsyncSession,
    *,
    trigger: str = "scheduled",
    jurisdiction: str | None = None,
    force: bool = False,
) -> NewsPollRun:
    started_at = datetime.now(timezone.utc)
    jurisdictions = _poll_jurisdictions(jurisdiction)
    target_key = _jurisdiction_key(jurisdictions)
    run = NewsPollRun(
        started_at=started_at,
        status="running",
        trigger=trigger,
        target_scope="current",
        target_key=target_key,
        interval_seconds=settings.news_poll_interval_seconds,
        notes=[f"Current news requested for {target_key}."],
    )
    session.add(run)
    await session.flush()

    try:
        recent = await _recent_completed_run(
            session,
            target_scope="current",
            target_key=target_key,
            max_age_seconds=settings.news_poll_interval_seconds,
        )
        if recent is not None and not force:
            run.status = "skipped"
            run.finished_at = datetime.now(timezone.utc)
            run.cache_hit = True
            run.notes = [
                *(run.notes or []),
                (
                    "Skipped provider calls; fresh current news exists from "
                    f"{recent.finished_at or recent.started_at}."
                ),
            ]
            await session.commit()
            await session.refresh(run)
            return run

        result = await fetch_current_news(
            jurisdictions=jurisdictions,
            us_tickers=[],
            ng_tickers=[],
            include_ticker_batches=False,
        )
        created, updated = await _upsert_provider_items(session, result.items)
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.provider_calls = result.calls
        run.provider_plan = result.provider_plan
        run.items_seen = len(result.items)
        run.items_created = created
        run.items_updated = updated
        run.errors = [{"error": message} for message in result.errors]
        run.notes = [
            *(run.notes or []),
            *result.notes,
            f"Polled current news for {target_key}.",
        ]
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("news_poll_failed")
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        run.errors = [{"error": str(exc)}]
        await session.commit()
        raise

    await session.refresh(run)
    return run


async def refresh_ticker_news(
    session: AsyncSession,
    *,
    ticker: str,
    market: str | None = None,
    force: bool = False,
) -> NewsPollRun:
    normalized = normalize_ticker(ticker, market)
    if not normalized:
        raise NewsUnavailableError("Ticker is required.")

    started_at = datetime.now(timezone.utc)
    run = NewsPollRun(
        started_at=started_at,
        status="running",
        trigger="ticker",
        target_scope="ticker",
        target_key=normalized,
        interval_seconds=settings.news_poll_interval_seconds,
        notes=[f"Ticker refresh requested for {normalized}."],
    )
    session.add(run)
    await session.flush()

    try:
        recent = await _recent_completed_run(
            session,
            target_scope="ticker",
            target_key=normalized,
            max_age_seconds=settings.news_ticker_refresh_ttl_seconds,
        )
        if recent is not None and not force:
            run.status = "skipped"
            run.finished_at = datetime.now(timezone.utc)
            run.cache_hit = True
            run.notes = [
                *(run.notes or []),
                (
                    "Skipped provider calls; fresh ticker news exists from "
                    f"{recent.finished_at or recent.started_at}."
                ),
            ]
            await session.commit()
            await session.refresh(run)
            return run

        result = await fetch_news_for_ticker(normalized, market=market)
        created, updated = await _upsert_provider_items(session, result.items)
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.provider_calls = result.calls
        run.provider_plan = result.provider_plan
        run.items_seen = len(result.items)
        run.items_created = created
        run.items_updated = updated
        run.errors = [{"error": message} for message in result.errors]
        run.notes = [*(run.notes or []), *result.notes]
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("ticker_news_refresh_failed", extra={"ticker": normalized})
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        run.errors = [{"error": str(exc)}]
        await session.commit()
        raise

    await session.refresh(run)
    return run


async def build_news_overview(
    session: AsyncSession,
    *,
    ticker: str | None = None,
    market: str | None = None,
    jurisdiction: str | None = None,
    owner_user_id: str | None = None,
) -> NewsOverviewResponse:
    generated_at = datetime.now(timezone.utc)
    latest_run = await _latest_run(session)
    normalized_ticker = normalize_ticker(ticker or "", market) if ticker else None
    normalized_jurisdiction = _normalize_jurisdiction(jurisdiction)

    current = await _current_items(session, jurisdiction=normalized_jurisdiction)
    ticker_items = (
        await _items_for_tickers(session, [normalized_ticker], limit=TICKER_NEWS_LIMIT)
        if normalized_ticker
        else []
    )
    watchlist_tickers = await _watchlist_tickers(session, owner_user_id)
    watchlist_items = (
        await _items_for_tickers(session, watchlist_tickers, limit=WATCHLIST_NEWS_LIMIT)
        if watchlist_tickers
        else []
    )

    return NewsOverviewResponse(
        generated_at=generated_at,
        latest_run=news_run_response(latest_run) if latest_run else None,
        current=[_item_response(item) for item in current],
        ticker=normalized_ticker,
        ticker_items=[_item_response(item) for item in ticker_items],
        watchlist_items=[_item_response(item) for item in watchlist_items],
        provider_notes=list(latest_run.notes or []) if latest_run else [],
    )


async def _news_targets(session: AsyncSession) -> tuple[list[str], list[str]]:
    tickers: set[str] = set()
    watched = await load_always_watched(session)
    tickers.update(watched.candidates.keys())

    latest_radar = await session.scalar(
        select(RadarRun)
        .options(selectinload(RadarRun.snapshots))
        .where(RadarRun.status == "completed")
        .where(RadarRun.working_set_count > 0)
        .order_by(RadarRun.started_at.desc())
        .limit(1)
    )
    if latest_radar is not None:
        tickers.update(
            snapshot.ticker
            for snapshot in latest_radar.snapshots
            if snapshot.in_working_set
        )

    us = sorted(ticker for ticker in tickers if jurisdiction_for_ticker(ticker) == "US")
    ng = sorted(ticker for ticker in tickers if jurisdiction_for_ticker(ticker) == "NG")
    return us, ng


async def _upsert_provider_items(
    session: AsyncSession,
    items: list[ProviderNewsItem],
) -> tuple[int, int]:
    created = 0
    updated = 0
    instrument_cache: dict[str, Instrument | None] = {}

    for provider_item in items:
        title = provider_item.title.strip()
        if not title:
            continue
        provider_id = provider_item.provider_id[:512]
        existing = await session.scalar(
            select(NewsItem)
            .options(selectinload(NewsItem.ticker_links))
            .where(NewsItem.provider == provider_item.provider)
            .where(NewsItem.provider_id == provider_id)
        )
        if existing is None:
            news_item = NewsItem(
                provider=provider_item.provider,
                provider_id=provider_id,
                source_name=_clip(provider_item.source_name, 255),
                title=title,
                summary=provider_item.summary,
                url=_clip(provider_item.url, 2048),
                published_at=provider_item.published_at,
                crawled_at=provider_item.crawled_at,
                jurisdiction=provider_item.jurisdiction,
                event_type=provider_item.event_type,
                sentiment_label=provider_item.sentiment_label,
                sentiment_score=provider_item.sentiment_score,
                raw_payload=provider_item.raw_payload,
            )
            session.add(news_item)
            await session.flush()
            linked_tickers: set[str] = set()
            created += 1
        else:
            news_item = existing
            linked_tickers = {link.ticker.upper() for link in news_item.ticker_links}
            changed = _apply_item_updates(news_item, provider_item)
            if changed:
                updated += 1

        for ticker in _normalized_tickers(provider_item):
            if ticker in linked_tickers:
                continue
            instrument = await _instrument_for_ticker(session, ticker, instrument_cache)
            session.add(
                NewsTickerLink(
                    news_item_id=news_item.id,
                    ticker=ticker,
                    instrument_id=instrument.id if instrument else None,
                    sentiment_label=provider_item.sentiment_label,
                    sentiment_score=provider_item.sentiment_score,
                )
            )
            linked_tickers.add(ticker)

    return created, updated


def _apply_item_updates(news_item: NewsItem, provider_item: ProviderNewsItem) -> bool:
    changed = False
    updates = {
        "source_name": _clip(provider_item.source_name, 255),
        "summary": provider_item.summary,
        "url": _clip(provider_item.url, 2048),
        "published_at": provider_item.published_at,
        "crawled_at": provider_item.crawled_at,
        "jurisdiction": provider_item.jurisdiction,
        "event_type": provider_item.event_type,
        "sentiment_label": provider_item.sentiment_label,
        "sentiment_score": provider_item.sentiment_score,
        "raw_payload": provider_item.raw_payload,
    }
    for field_name, value in updates.items():
        if value is not None and getattr(news_item, field_name) != value:
            setattr(news_item, field_name, value)
            changed = True
    return changed


async def _instrument_for_ticker(
    session: AsyncSession,
    ticker: str,
    cache: dict[str, Instrument | None],
) -> Instrument | None:
    if ticker in cache:
        return cache[ticker]

    instrument = await session.scalar(select(Instrument).where(Instrument.ticker == ticker))
    if instrument is None and ticker.endswith(".NG"):
        instrument = await session.scalar(
            select(Instrument).where(Instrument.ticker == ticker.removesuffix(".NG"))
        )
    cache[ticker] = instrument
    return cache[ticker]


async def _latest_run(session: AsyncSession) -> NewsPollRun | None:
    return await session.scalar(
        select(NewsPollRun).order_by(NewsPollRun.started_at.desc()).limit(1)
    )


async def _recent_completed_run(
    session: AsyncSession,
    *,
    target_scope: str,
    target_key: str,
    max_age_seconds: int,
) -> NewsPollRun | None:
    fresh_after = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    return await session.scalar(
        select(NewsPollRun)
        .where(NewsPollRun.status == "completed")
        .where(NewsPollRun.target_scope == target_scope)
        .where(NewsPollRun.target_key == target_key)
        .where(NewsPollRun.started_at >= fresh_after)
        .order_by(NewsPollRun.started_at.desc())
        .limit(1)
    )


async def _current_items(
    session: AsyncSession,
    *,
    jurisdiction: str | None,
) -> list[NewsItem]:
    query = (
        select(NewsItem)
        .options(selectinload(NewsItem.ticker_links))
        .order_by(
            NewsItem.published_at.desc().nullslast(),
            NewsItem.created_at.desc(),
        )
        .limit(CURRENT_NEWS_LIMIT)
    )
    if jurisdiction in {"US", "NG"}:
        query = query.where(NewsItem.jurisdiction == jurisdiction)
    return list(await session.scalars(query))


async def _items_for_tickers(
    session: AsyncSession,
    tickers: list[str | None],
    *,
    limit: int,
) -> list[NewsItem]:
    normalized = [ticker for ticker in {item for item in tickers if item} if ticker]
    if not normalized:
        return []
    rows = list(
        await session.scalars(
            select(NewsItem)
            .join(NewsTickerLink, NewsTickerLink.news_item_id == NewsItem.id)
            .options(selectinload(NewsItem.ticker_links))
            .where(NewsTickerLink.ticker.in_(normalized))
            .order_by(
                NewsItem.published_at.desc().nullslast(),
                NewsItem.created_at.desc(),
            )
            .limit(limit)
        )
    )
    deduped: list[NewsItem] = []
    seen: set = set()
    for item in rows:
        if item.id in seen:
            continue
        seen.add(item.id)
        deduped.append(item)
    return deduped


async def _watchlist_tickers(
    session: AsyncSession,
    owner_user_id: str | None,
) -> list[str]:
    if not owner_user_id:
        return []
    rows = await session.scalars(
        select(RadarWatchlistItem.ticker).where(
            RadarWatchlistItem.owner_user_id == owner_user_id
        )
    )
    return [ticker.upper() for ticker in rows]


def _item_response(item: NewsItem) -> NewsItemResponse:
    return NewsItemResponse(
        id=item.id,
        provider=item.provider,
        provider_id=item.provider_id,
        source_name=item.source_name,
        title=item.title,
        summary=item.summary,
        url=item.url,
        published_at=item.published_at,
        crawled_at=item.crawled_at,
        jurisdiction=item.jurisdiction,
        event_type=item.event_type,
        sentiment_label=item.sentiment_label,
        sentiment_score=item.sentiment_score,
        tickers=sorted({link.ticker for link in item.ticker_links}),
    )


def news_run_response(run: NewsPollRun) -> NewsPollRunResponse:
    return NewsPollRunResponse(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        trigger=run.trigger,
        target_scope=run.target_scope,
        target_key=run.target_key,
        provider_calls=run.provider_calls,
        items_seen=run.items_seen,
        items_created=run.items_created,
        items_updated=run.items_updated,
        interval_seconds=run.interval_seconds,
        cache_hit=run.cache_hit,
        provider_plan=list(run.provider_plan or []),
        errors=list(run.errors or []),
        notes=list(run.notes or []),
    )


def _normalized_tickers(provider_item: ProviderNewsItem) -> list[str]:
    tickers: list[str] = []
    for ticker in provider_item.tickers:
        market = (
            "NG"
            if provider_item.jurisdiction == "NG" or ticker.endswith(".NG")
            else None
        )
        normalized = normalize_ticker(ticker, market)
        if normalized and normalized not in tickers:
            tickers.append(normalized)
    return tickers


def _normalize_jurisdiction(value: str | None) -> str | None:
    normalized = (value or "all").strip().upper()
    if normalized in {"US", "NG"}:
        return normalized
    return None


def _poll_jurisdictions(value: str | None) -> tuple[str, ...]:
    if value is None:
        return settings.news_poll_jurisdictions
    normalized = value.strip().upper()
    if normalized == "ALL":
        return ("US", "NG")
    if normalized in {"US", "NG"}:
        return (normalized,)
    return settings.news_poll_jurisdictions


def _jurisdiction_key(jurisdictions: tuple[str, ...]) -> str:
    ordered = [item for item in ("US", "NG") if item in jurisdictions]
    return ",".join(ordered) or "US"


def _clip(value: str | None, length: int) -> str | None:
    if value is None:
        return None
    return value[:length]
