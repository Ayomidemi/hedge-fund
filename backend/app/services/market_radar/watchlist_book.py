"""Operator watchlist: manual membership, always watched by radar."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.market_radar import (
    RadarWatchlistChartPoint,
    RadarWatchlistChartResponse,
    RadarWatchlistClockResponse,
    RadarWatchlistCreateRequest,
    RadarWatchlistDetailResponse,
    RadarWatchlistItemResponse,
    RadarWatchlistListResponse,
)
from app.api.schemas.operating_core import InstrumentCreate
from app.core.config import settings
from app.core.market_constants import (
    QUOTE_HTTP_TIMEOUT_SECONDS,
    RADAR_CHART_LOOKBACK_DAYS,
    RADAR_CHART_MIN_BARS,
    RADAR_CHART_RANGES,
)
from app.models import (
    Instrument,
    MarketPriceBar,
    RadarRun,
    RadarSnapshot,
    RadarUniverseMember,
    RadarWatchlistItem,
)
from app.services.market_data.sessions import JURISDICTION_NG, jurisdiction_for_ticker
from app.services.market_data.universe import quote_symbol_for
from app.services.portfolio.operating_core import upsert_instrument

logger = logging.getLogger(__name__)

CHART_SOURCE_PRIORITY = (
    "tiingo",
    "live",
    "ngnmarket",
    "polygon",
    "fmp",
    "yahoo",
)


class WatchlistError(RuntimeError):
    pass


class WatchlistNotFoundError(WatchlistError):
    pass


class WatchlistValidationError(WatchlistError):
    pass


async def list_watchlist(
    session: AsyncSession,
    *,
    owner_user_id: str,
) -> RadarWatchlistListResponse:
    items = await _load_items(session, owner_user_id)
    snapshots = await _latest_snapshots(session, {item.ticker for item in items})
    return RadarWatchlistListResponse(
        items=[_item_response(item, snapshots.get(item.ticker)) for item in items]
    )


async def add_watchlist_item(
    session: AsyncSession,
    *,
    owner_user_id: str,
    payload: RadarWatchlistCreateRequest,
) -> RadarWatchlistItemResponse:
    ticker = _normalize_ticker(payload.ticker, payload.market)
    if not ticker:
        raise WatchlistValidationError("Enter a ticker.")

    existing = await session.scalar(
        select(RadarWatchlistItem)
        .where(RadarWatchlistItem.owner_user_id == owner_user_id)
        .where(RadarWatchlistItem.ticker == ticker)
    )
    if existing is not None:
        if payload.notes is not None:
            existing.notes = payload.notes
            await session.commit()
        snapshots = await _latest_snapshots(session, {existing.ticker})
        return _item_response(existing, snapshots.get(existing.ticker))

    identity = await _resolve_identity(session, ticker)
    instrument = await upsert_instrument(
        session,
        InstrumentCreate(
            ticker=identity["ticker"],
            name=identity["name"][:255],
            asset_class=identity["asset_class"],
            exchange=identity["exchange"],
            currency=identity["currency"],
            sector=identity["sector"],
            industry=identity["industry"],
        ),
    )
    item = RadarWatchlistItem(
        owner_user_id=owner_user_id,
        ticker=quote_symbol_for(instrument),
        name=instrument.name,
        jurisdiction=jurisdiction_for_ticker(quote_symbol_for(instrument)),
        notes=payload.notes,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    snapshots = await _latest_snapshots(session, {item.ticker})
    return _item_response(item, snapshots.get(item.ticker))


async def remove_watchlist_item(
    session: AsyncSession,
    *,
    owner_user_id: str,
    ticker: str,
) -> None:
    item = await _get_item(session, owner_user_id, ticker)
    await session.delete(item)
    await session.commit()


async def get_watchlist_detail(
    session: AsyncSession,
    *,
    owner_user_id: str,
    ticker: str,
) -> RadarWatchlistDetailResponse:
    item = await _get_item(session, owner_user_id, ticker)
    snapshots = await _latest_snapshots(session, {item.ticker})
    snapshot = snapshots.get(item.ticker)
    return RadarWatchlistDetailResponse(
        **_item_response(item, snapshot).model_dump(),
        clocks=_clocks(snapshot),
    )


async def get_watchlist_chart(
    session: AsyncSession,
    *,
    owner_user_id: str,
    ticker: str,
    range_key: str,
) -> RadarWatchlistChartResponse:
    item = await _get_item(session, owner_user_id, ticker)
    normalized_range = (range_key or "1d").lower()
    if normalized_range not in RADAR_CHART_RANGES:
        raise WatchlistValidationError(
            f"Range must be one of {', '.join(RADAR_CHART_RANGES)}."
        )
    if normalized_range == "1d":
        return await _intraday_film(session, item)

    return await _daily_chart(session, item, normalized_range)


async def watchlist_tickers_for_owner(
    session: AsyncSession,
    owner_user_id: str,
) -> set[str]:
    rows = await session.scalars(
        select(RadarWatchlistItem.ticker).where(
            RadarWatchlistItem.owner_user_id == owner_user_id
        )
    )
    return {ticker.upper() for ticker in rows}


async def _load_items(
    session: AsyncSession, owner_user_id: str
) -> list[RadarWatchlistItem]:
    return list(
        await session.scalars(
            select(RadarWatchlistItem)
            .where(RadarWatchlistItem.owner_user_id == owner_user_id)
            .order_by(RadarWatchlistItem.created_at.desc())
        )
    )


async def _get_item(
    session: AsyncSession, owner_user_id: str, ticker: str
) -> RadarWatchlistItem:
    normalized = ticker.strip().upper()
    variants = {normalized, normalized.removesuffix(".NG"), f"{normalized.removesuffix('.NG')}.NG"}
    item = await session.scalar(
        select(RadarWatchlistItem)
        .where(RadarWatchlistItem.owner_user_id == owner_user_id)
        .where(RadarWatchlistItem.ticker.in_(variants))
    )
    if item is None:
        raise WatchlistNotFoundError(f"{normalized} is not on the watchlist.")
    return item


async def _resolve_identity(session: AsyncSession, ticker: str) -> dict[str, str | None]:
    member = await session.scalar(
        select(RadarUniverseMember).where(RadarUniverseMember.ticker == ticker)
    )
    if member is not None:
        return {
            "ticker": member.ticker,
            "name": member.name,
        "asset_class": (
            member.asset_class
            if member.asset_class
            in {"equity", "etf", "bond", "commodity", "cash_equivalent", "other"}
            else "equity"
        ),
            "exchange": member.exchange,
            "currency": member.currency or ("NGN" if member.jurisdiction == JURISDICTION_NG else "USD"),
            "sector": member.sector,
            "industry": member.industry,
        }

    instrument = await session.scalar(select(Instrument).where(Instrument.ticker == ticker))
    if instrument is None and ticker.endswith(".NG"):
        instrument = await session.scalar(
            select(Instrument).where(Instrument.ticker == ticker.removesuffix(".NG"))
        )
    if instrument is not None:
        return {
            "ticker": quote_symbol_for(instrument),
            "name": instrument.name,
            "asset_class": instrument.asset_class
            if instrument.asset_class
            in {"equity", "etf", "bond", "commodity", "cash_equivalent", "other"}
            else "equity",
            "exchange": instrument.exchange,
            "currency": instrument.currency,
            "sector": instrument.sector,
            "industry": instrument.industry,
        }

    jurisdiction = jurisdiction_for_ticker(ticker)
    return {
        "ticker": ticker,
        "name": ticker,
        "asset_class": "equity",
        "exchange": "NGX" if jurisdiction == JURISDICTION_NG else None,
        "currency": "NGN" if jurisdiction == JURISDICTION_NG else "USD",
        "sector": None,
        "industry": None,
    }


async def _latest_snapshots(
    session: AsyncSession, tickers: set[str]
) -> dict[str, RadarSnapshot]:
    if not tickers:
        return {}
    rows = await session.scalars(
        select(RadarSnapshot)
        .join(RadarRun, RadarRun.id == RadarSnapshot.run_id)
        .where(RadarRun.status == "completed")
        .where(RadarSnapshot.ticker.in_(tickers))
        .order_by(RadarSnapshot.as_of.desc())
    )
    latest: dict[str, RadarSnapshot] = {}
    for row in rows:
        if row.ticker not in latest:
            latest[row.ticker] = row
    return latest


async def _intraday_film(
    session: AsyncSession, item: RadarWatchlistItem
) -> RadarWatchlistChartResponse:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = list(
        await session.scalars(
            select(RadarSnapshot)
            .join(RadarRun, RadarRun.id == RadarSnapshot.run_id)
            .where(RadarRun.status == "completed")
            .where(RadarSnapshot.ticker == item.ticker)
            .where(RadarSnapshot.as_of >= start)
            .where(RadarSnapshot.carried_forward.is_(False))
            .order_by(RadarSnapshot.as_of.asc())
        )
    )
    note = None
    if not rows:
        rows = list(
            await session.scalars(
                select(RadarSnapshot)
                .join(RadarRun, RadarRun.id == RadarSnapshot.run_id)
                .where(RadarRun.status == "completed")
                .where(RadarSnapshot.ticker == item.ticker)
                .where(RadarSnapshot.carried_forward.is_(False))
                .order_by(RadarSnapshot.as_of.desc())
                .limit(12)
            )
        )
        rows.reverse()
        note = "No same-day radar film yet. Showing the latest scans."
    return RadarWatchlistChartResponse(
        ticker=item.ticker,
        range="1d",
        source="radar_snapshots",
        filled_from_vendor=False,
        note=note,
        points=[
            RadarWatchlistChartPoint(
                at=row.source_as_of or row.as_of,
                date=(row.source_as_of or row.as_of).date().isoformat(),
                price=row.price,
                volume=row.volume,
                change_pct=row.change_pct,
                source=row.source,
            )
            for row in rows
            if row.price is not None
        ],
    )


async def _daily_chart(
    session: AsyncSession,
    item: RadarWatchlistItem,
    range_key: str,
) -> RadarWatchlistChartResponse:
    lookback = RADAR_CHART_LOOKBACK_DAYS[range_key]
    start = date.today() - timedelta(days=lookback)
    instrument = await _instrument_for_ticker(session, item.ticker)
    filled = False
    source = "market_price_bars"
    note = None

    if instrument is None:
        return RadarWatchlistChartResponse(
            ticker=item.ticker,
            range=range_key,
            source=source,
            filled_from_vendor=False,
            note="No stored bars yet. Radar will persist a tape once this name prints.",
            points=[],
        )

    points = await _bars_as_points(session, instrument.id, start)
    min_bars = RADAR_CHART_MIN_BARS.get(range_key, 10)
    if (
        item.jurisdiction != JURISDICTION_NG
        and len(points) < min_bars
        and settings.hf_tiingo_api_key
    ):
        saved = await _fill_tiingo_daily(session, instrument, start)
        if saved:
            filled = True
            source = "tiingo"
            points = await _bars_as_points(session, instrument.id, start)
    elif item.jurisdiction == JURISDICTION_NG and len(points) < min_bars:
        note = "NGX charts use stored bars only. No US vendor is called."

    return RadarWatchlistChartResponse(
        ticker=item.ticker,
        range=range_key,
        source=source,
        filled_from_vendor=filled,
        note=note,
        points=points,
    )


async def _bars_as_points(
    session: AsyncSession, instrument_id, start: date
) -> list[RadarWatchlistChartPoint]:
    rows = list(
        await session.scalars(
            select(MarketPriceBar)
            .where(MarketPriceBar.instrument_id == instrument_id)
            .where(MarketPriceBar.bar_date >= start)
            .order_by(MarketPriceBar.bar_date.asc(), MarketPriceBar.source.asc())
        )
    )
    by_date: dict[date, MarketPriceBar] = {}
    for bar in rows:
        current = by_date.get(bar.bar_date)
        if current is None or _source_rank(bar.source) < _source_rank(current.source):
            by_date[bar.bar_date] = bar
    points: list[RadarWatchlistChartPoint] = []
    previous: Decimal | None = None
    for bar_date in sorted(by_date):
        bar = by_date[bar_date]
        change = None
        if previous is not None and previous > 0:
            change = ((bar.close_price - previous) / previous * Decimal("100")).quantize(
                Decimal("0.01")
            )
        points.append(
            RadarWatchlistChartPoint(
                date=bar.bar_date.isoformat(),
                price=bar.close_price,
                volume=bar.volume,
                change_pct=change,
                source=bar.source,
            )
        )
        previous = bar.close_price
    return points


async def _fill_tiingo_daily(
    session: AsyncSession, instrument: Instrument, start: date
) -> int:
    symbol = instrument.ticker.removesuffix(".NG").lower()
    try:
        async with httpx.AsyncClient(
            base_url=settings.tiingo_base_url,
            timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
            headers={"Authorization": f"Token {settings.hf_tiingo_api_key}"},
        ) as client:
            response = await client.get(
                f"/tiingo/daily/{symbol}/prices",
                params={
                    "startDate": start.isoformat(),
                    "endDate": date.today().isoformat(),
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.warning("tiingo_watchlist_chart_failed", extra={"error": str(exc)})
        return 0

    if not isinstance(payload, list) or not payload:
        return 0

    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        close_price = _decimal(item.get("adjClose") or item.get("close"))
        if close_price is None:
            continue
        bar_date = _parse_date(item.get("date"))
        if bar_date is None:
            continue
        rows.append(
            {
                "instrument_id": instrument.id,
                "bar_date": bar_date,
                "source": "tiingo",
                "open_price": _decimal(item.get("adjOpen") or item.get("open")),
                "high_price": _decimal(item.get("adjHigh") or item.get("high")),
                "low_price": _decimal(item.get("adjLow") or item.get("low")),
                "close_price": close_price,
                "adjusted_close_price": _decimal(item.get("adjClose")),
                "volume": int(item["volume"]) if item.get("volume") is not None else None,
                "currency": instrument.currency,
                "raw_payload": item,
            }
        )
    if not rows:
        return 0
    statement = insert(MarketPriceBar).values(rows)
    statement = statement.on_conflict_do_update(
        constraint="uq_market_price_bars_instrument_date_source",
        set_={
            "open_price": statement.excluded.open_price,
            "high_price": statement.excluded.high_price,
            "low_price": statement.excluded.low_price,
            "close_price": statement.excluded.close_price,
            "adjusted_close_price": statement.excluded.adjusted_close_price,
            "volume": statement.excluded.volume,
            "currency": statement.excluded.currency,
            "raw_payload": statement.excluded.raw_payload,
        },
    )
    await session.execute(statement)
    await session.commit()
    return len(rows)


async def _instrument_for_ticker(
    session: AsyncSession, ticker: str
) -> Instrument | None:
    variants = {ticker, ticker.removesuffix(".NG")}
    return await session.scalar(select(Instrument).where(Instrument.ticker.in_(variants)))


def _item_response(
    item: RadarWatchlistItem, snapshot: RadarSnapshot | None
) -> RadarWatchlistItemResponse:
    evidence = dict(snapshot.evidence or {}) if snapshot else {}
    return RadarWatchlistItemResponse(
        ticker=item.ticker,
        name=item.name,
        jurisdiction=item.jurisdiction,
        notes=item.notes,
        added_at=item.created_at,
        on_watchlist=True,
        price=snapshot.price if snapshot else None,
        change_pct=snapshot.change_pct if snapshot else None,
        volume=snapshot.volume if snapshot else None,
        volume_ratio=snapshot.volume_ratio if snapshot else None,
        anomaly_score=snapshot.anomaly_score if snapshot else None,
        flags=list(snapshot.flags or []) if snapshot else [],
        evidence=evidence,
        sparkline=list(snapshot.sparkline or []) if snapshot else [],
        as_of=snapshot.as_of if snapshot else None,
        source_as_of=snapshot.source_as_of if snapshot else None,
        carried_forward=bool(snapshot.carried_forward) if snapshot else False,
        scan_state=str(evidence["scan_state"]) if evidence.get("scan_state") else None,
        scan_delta_change_pct=_decimal(evidence.get("scan_delta_change_pct")),
        scan_delta_price_pct=_decimal(evidence.get("scan_delta_price_pct")),
    )


def _clocks(snapshot: RadarSnapshot | None) -> dict[str, RadarWatchlistClockResponse]:
    evidence = dict(snapshot.evidence or {}) if snapshot else {}
    return {
        "vs_yesterday": RadarWatchlistClockResponse(
            label="vs yesterday",
            change_pct=snapshot.change_pct if snapshot else None,
        ),
        "vs_own_history": RadarWatchlistClockResponse(
            label="vs own history",
            price_return_zscore=evidence.get("price_return_zscore"),
            volume_zscore=evidence.get("volume_zscore"),
            volatility_ratio=evidence.get("volatility_ratio"),
        ),
        "vs_last_radar": RadarWatchlistClockResponse(
            label="vs last radar",
            scan_state=evidence.get("scan_state"),
            scan_delta_change_pct=evidence.get("scan_delta_change_pct"),
            scan_delta_price_pct=evidence.get("scan_delta_price_pct"),
            scan_minutes_since_prior=evidence.get("scan_minutes_since_prior"),
        ),
    }


def _normalize_ticker(ticker: str, market: str | None) -> str:
    value = ticker.strip().upper()
    if not value:
        return ""
    if market == "NG" and not value.endswith(".NG"):
        value = f"{value}.NG"
    if market == "US" and value.endswith(".NG"):
        value = value.removesuffix(".NG")
    return value


def _source_rank(source: str) -> int:
    try:
        return CHART_SOURCE_PRIORITY.index(source)
    except ValueError:
        return len(CHART_SOURCE_PRIORITY) + 1


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
