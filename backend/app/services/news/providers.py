from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings
from app.core.market_constants import QUOTE_HTTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

NEWS_FEED_LIMIT = 50
NEWS_TICKER_BATCH_LIMIT = 40
NEWS_TICKER_REFRESH_LIMIT = 25
NGN_TARGET_POLL_LIMIT = 8


@dataclass(frozen=True)
class NewsFetchResult:
    items: list["ProviderNewsItem"] = field(default_factory=list)
    calls: int = 0
    provider_plan: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderNewsItem:
    provider: str
    provider_id: str
    title: str
    url: str | None = None
    summary: str | None = None
    source_name: str | None = None
    published_at: datetime | None = None
    crawled_at: datetime | None = None
    tickers: tuple[str, ...] = ()
    jurisdiction: str | None = None
    event_type: str | None = None
    sentiment_label: str | None = None
    sentiment_score: Decimal | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NewsFetch:
    label: str
    run: Callable[[], Awaitable[NewsFetchResult]]


async def fetch_current_news(
    *,
    jurisdictions: list[str] | tuple[str, ...],
    us_tickers: list[str],
    ng_tickers: list[str],
    include_ticker_batches: bool = False,
) -> NewsFetchResult:
    """Fetch a bounded, explicitly scoped current-news batch."""
    requested = _normalize_jurisdictions(jurisdictions)
    fetches: list[NewsFetch] = []

    if "US" in requested:
        fetches.extend(
            [
                NewsFetch(
                    "US:tiingo:latest",
                    lambda: _fetch_tiingo_news(tickers=[]),
                ),
                NewsFetch(
                    "US:fmp:stock-latest",
                    lambda: _fetch_fmp_latest_news(
                        include_general=False,
                        include_press_releases=False,
                    ),
                ),
            ]
        )
        if include_ticker_batches and us_tickers:
            us_batch = us_tickers[:NEWS_TICKER_BATCH_LIMIT]
            fetches.append(
                NewsFetch(
                    f"US:tiingo:ticker-batch:{len(us_batch)}",
                    lambda tickers=us_batch: _fetch_tiingo_news(tickers=tickers),
                )
            )

    if "NG" in requested:
        fetches.append(
            NewsFetch(
                "NG:ngnmarket:disclosures",
                lambda: _fetch_ngn_disclosures(symbol=None),
            )
        )
        if include_ticker_batches:
            for ticker in ng_tickers[:NGN_TARGET_POLL_LIMIT]:
                fetches.append(
                    NewsFetch(
                        f"NG:ngnmarket:company:{ticker.removesuffix('.NG')}",
                        lambda symbol=ticker: _fetch_ngn_company_news(symbol),
                    )
                )

    results = await _gather_results(fetches)
    notes = list(results.notes)
    if include_ticker_batches and len(ng_tickers) > NGN_TARGET_POLL_LIMIT:
        notes.append(
            f"NG ticker news capped at {NGN_TARGET_POLL_LIMIT} symbols this poll."
        )
    return NewsFetchResult(
        items=results.items,
        calls=results.calls,
        provider_plan=results.provider_plan,
        errors=results.errors,
        notes=notes,
    )


async def fetch_news_for_ticker(
    ticker: str, *, market: str | None = None
) -> NewsFetchResult:
    normalized = normalize_ticker(ticker, market)
    jurisdiction = "NG" if normalized.endswith(".NG") else "US"
    symbol = normalized.removesuffix(".NG") if jurisdiction == "NG" else normalized
    if jurisdiction == "NG":
        return await _gather_results(
            [
                NewsFetch(
                    f"NG:ngnmarket:company:{symbol}",
                    lambda: _fetch_ngn_company_news(symbol),
                ),
                NewsFetch(
                    f"NG:ngnmarket:disclosures:{symbol}",
                    lambda: _fetch_ngn_disclosures(symbol=symbol),
                ),
            ]
        )

    fetches = [
        NewsFetch(
            f"US:tiingo:ticker:{symbol}",
            lambda: _fetch_tiingo_news(tickers=[symbol]),
        ),
        NewsFetch(
            f"US:fmp:ticker-stock:{symbol}",
            lambda: _fetch_fmp_ticker_news(symbol, include_press_releases=False),
        ),
    ]
    if not settings.hf_tiingo_api_key and settings.hf_polygon_api_key:
        fetches.append(
            NewsFetch(
                f"US:polygon:ticker:{symbol}",
                lambda: _fetch_polygon_ticker_news(symbol),
            )
        )
    return await _gather_results(fetches)


def normalize_ticker(ticker: str, market: str | None = None) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        return ""
    if market == "NG" and not normalized.endswith(".NG"):
        return f"{normalized}.NG"
    return normalized


def _normalize_jurisdictions(
    jurisdictions: list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    normalized: list[str] = []
    for jurisdiction in jurisdictions:
        item = jurisdiction.strip().upper()
        if item in {"US", "NG"} and item not in normalized:
            normalized.append(item)
    return tuple(normalized) or ("US",)


async def _gather_results(fetches: list[NewsFetch]) -> NewsFetchResult:
    items: list[ProviderNewsItem] = []
    calls = 0
    provider_plan: list[str] = []
    errors: list[str] = []
    notes: list[str] = []
    for fetch in fetches:
        provider_plan.append(fetch.label)
        result = await fetch.run()
        items.extend(result.items)
        calls += result.calls
        provider_plan.extend(
            item for item in result.provider_plan if item not in provider_plan
        )
        errors.extend(result.errors)
        notes.extend(result.notes)
    return NewsFetchResult(
        items=items,
        calls=calls,
        provider_plan=provider_plan,
        errors=errors,
        notes=notes,
    )


async def _fetch_tiingo_news(tickers: list[str]) -> NewsFetchResult:
    if not settings.hf_tiingo_api_key:
        return NewsFetchResult(notes=["Tiingo news skipped: API key missing."])

    params: dict[str, str | int] = {
        "limit": NEWS_FEED_LIMIT,
        "sortBy": "publishedDate",
    }
    if tickers:
        params["tickers"] = ",".join(
            ticker.lower().removesuffix(".ng") for ticker in tickers
        )
        params["onlyWithTickers"] = "true"

    try:
        async with httpx.AsyncClient(
            base_url=settings.tiingo_base_url,
            timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
            headers={"Authorization": f"Token {settings.hf_tiingo_api_key}"},
        ) as client:
            response = await client.get("/tiingo/news", params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("tiingo_news_failed", extra={"error": str(exc)})
        return NewsFetchResult(calls=1, errors=[f"Tiingo news failed: {exc}"])

    rows = payload if isinstance(payload, list) else []
    return NewsFetchResult(
        calls=1,
        items=[_tiingo_item(row) for row in rows if isinstance(row, dict)],
    )


async def _fetch_polygon_ticker_news(ticker: str) -> NewsFetchResult:
    if not settings.hf_polygon_api_key:
        return NewsFetchResult(notes=["Polygon news skipped: API key missing."])

    try:
        async with httpx.AsyncClient(
            base_url=settings.polygon_base_url,
            timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
            headers={"Authorization": f"Bearer {settings.hf_polygon_api_key}"},
        ) as client:
            response = await client.get(
                "/v2/reference/news",
                params={
                    "ticker": ticker,
                    "limit": str(NEWS_TICKER_REFRESH_LIMIT),
                    "sort": "published_utc",
                    "order": "desc",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "polygon_news_failed", extra={"ticker": ticker, "error": str(exc)}
        )
        return NewsFetchResult(
            calls=1, errors=[f"Polygon news failed for {ticker}: {exc}"]
        )

    rows = _list_payload(payload)
    return NewsFetchResult(
        calls=1,
        items=[_polygon_item(row) for row in rows if isinstance(row, dict)],
    )


async def _fetch_fmp_latest_news(
    *,
    include_general: bool,
    include_press_releases: bool,
) -> NewsFetchResult:
    if not settings.hf_fmp_api_key:
        return NewsFetchResult(notes=["FMP news skipped: API key missing."])

    base_url = settings.fmp_base_url.removesuffix("/api")
    items: list[ProviderNewsItem] = []
    calls = 0
    errors: list[str] = []
    endpoints = [("/stable/news/stock-latest", "market_news")]
    if include_general:
        endpoints.append(("/stable/news/general-latest", "general_news"))
    if include_press_releases:
        endpoints.append(("/stable/news/press-releases-latest", "press_release"))

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
    ) as client:
        for path, event_type in endpoints:
            calls += 1
            try:
                response = await client.get(
                    path,
                    params={
                        "page": "0",
                        "limit": str(NEWS_FEED_LIMIT),
                        "apikey": settings.hf_fmp_api_key,
                    },
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning(
                    "fmp_news_failed", extra={"path": path, "error": str(exc)}
                )
                errors.append(f"FMP {path} failed: {exc}")
                continue
            rows = _list_payload(payload)
            items.extend(
                _fmp_item(row, event_type=event_type)
                for row in rows
                if isinstance(row, dict)
            )
    return NewsFetchResult(items=items, calls=calls, errors=errors)


async def _fetch_fmp_ticker_news(
    ticker: str,
    *,
    include_press_releases: bool,
) -> NewsFetchResult:
    if not settings.hf_fmp_api_key:
        return NewsFetchResult(notes=["FMP ticker news skipped: API key missing."])

    base_url = settings.fmp_base_url.removesuffix("/api")
    items: list[ProviderNewsItem] = []
    calls = 0
    errors: list[str] = []
    endpoints = [
        (
            "/stable/news/stock",
            {"symbols": ticker, "apikey": settings.hf_fmp_api_key},
            "market_news",
        )
    ]
    if include_press_releases:
        endpoints.append(
            (
                "/stable/news/press-releases",
                {"symbols": ticker, "apikey": settings.hf_fmp_api_key},
                "press_release",
            )
        )

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
    ) as client:
        for path, params, event_type in endpoints:
            calls += 1
            try:
                response = await client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning(
                    "fmp_ticker_news_failed",
                    extra={"path": path, "error": str(exc)},
                )
                errors.append(f"FMP {path} failed for {ticker}: {exc}")
                continue
            rows = _list_payload(payload)
            items.extend(
                _fmp_item(row, event_type=event_type)
                for row in rows[:NEWS_TICKER_REFRESH_LIMIT]
                if isinstance(row, dict)
            )
    return NewsFetchResult(items=items, calls=calls, errors=errors)


async def _fetch_ngn_company_news(symbol: str) -> NewsFetchResult:
    if not settings.hf_ngnmarket_api_key:
        return NewsFetchResult(notes=["NGN Market news skipped: API key missing."])

    clean_symbol = symbol.upper().removesuffix(".NG")
    try:
        async with httpx.AsyncClient(
            base_url=settings.ngnmarket_base_url,
            timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
            headers={"Authorization": f"Bearer {settings.hf_ngnmarket_api_key}"},
        ) as client:
            response = await client.get(
                f"/companies/{clean_symbol}/news",
                params={"maxAge": "14d", "limit": str(NEWS_TICKER_REFRESH_LIMIT)},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "ngn_company_news_failed",
            extra={"symbol": clean_symbol, "error": str(exc)},
        )
        return NewsFetchResult(
            calls=1, errors=[f"NGN Market news failed for {clean_symbol}: {exc}"]
        )

    rows = _ngn_rows(payload)
    return NewsFetchResult(
        calls=1,
        items=[
            _ngn_item(row, ticker=f"{clean_symbol}.NG", event_type="market_news")
            for row in rows
            if isinstance(row, dict)
        ],
    )


async def _fetch_ngn_disclosures(symbol: str | None) -> NewsFetchResult:
    if not settings.hf_ngnmarket_api_key:
        return NewsFetchResult(notes=["NGN Market disclosures skipped: API key missing."])

    params: dict[str, str] = {"limit": str(NEWS_FEED_LIMIT)}
    if symbol:
        params["symbol"] = symbol.upper().removesuffix(".NG")
    try:
        async with httpx.AsyncClient(
            base_url=settings.ngnmarket_base_url,
            timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
            headers={"Authorization": f"Bearer {settings.hf_ngnmarket_api_key}"},
        ) as client:
            response = await client.get("/disclosures", params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "ngn_disclosures_failed", extra={"symbol": symbol, "error": str(exc)}
        )
        target = f" for {symbol}" if symbol else ""
        return NewsFetchResult(
            calls=1, errors=[f"NGN disclosures failed{target}: {exc}"]
        )

    rows = _ngn_rows(payload)
    return NewsFetchResult(
        calls=1,
        items=[
            _ngn_item(row, ticker=symbol, event_type="filing")
            for row in rows
            if isinstance(row, dict)
        ],
    )


def _tiingo_item(row: dict[str, Any]) -> ProviderNewsItem:
    tickers = _tickers(row.get("tickers"))
    return ProviderNewsItem(
        provider="tiingo",
        provider_id=str(row.get("id") or _fallback_id("tiingo", row)),
        title=_string(row.get("title")) or "Untitled news item",
        url=_string(row.get("url")),
        summary=_string(row.get("description")),
        source_name=_string(row.get("source")),
        published_at=_parse_datetime(row.get("publishedDate")),
        crawled_at=_parse_datetime(row.get("crawlDate")),
        tickers=tuple(tickers),
        jurisdiction="US" if tickers else None,
        event_type="market_news",
        raw_payload=row,
    )


def _polygon_item(row: dict[str, Any]) -> ProviderNewsItem:
    insights = row.get("insights") if isinstance(row.get("insights"), list) else []
    first_insight = next((item for item in insights if isinstance(item, dict)), {})
    sentiment = _string(first_insight.get("sentiment"))
    publisher = row.get("publisher") if isinstance(row.get("publisher"), dict) else {}
    return ProviderNewsItem(
        provider="polygon",
        provider_id=str(row.get("id") or _fallback_id("polygon", row)),
        title=_string(row.get("title")) or "Untitled news item",
        url=_string(row.get("article_url") or row.get("amp_url")),
        summary=_string(row.get("description")),
        source_name=_string(publisher.get("name")),
        published_at=_parse_datetime(row.get("published_utc")),
        tickers=tuple(_tickers(row.get("tickers"))),
        jurisdiction="US",
        event_type="market_news",
        sentiment_label=sentiment.lower() if sentiment else None,
        raw_payload=row,
    )


def _fmp_item(row: dict[str, Any], *, event_type: str) -> ProviderNewsItem:
    tickers = _tickers(
        row.get("symbols")
        or row.get("symbol")
        or row.get("tickers")
        or row.get("ticker")
    )
    return ProviderNewsItem(
        provider="fmp",
        provider_id=str(row.get("id") or row.get("url") or _fallback_id("fmp", row)),
        title=_string(row.get("title")) or "Untitled news item",
        url=_string(row.get("url") or row.get("link")),
        summary=_string(row.get("text") or row.get("summary") or row.get("snippet")),
        source_name=_string(row.get("site") or row.get("publisher") or row.get("source")),
        published_at=_parse_datetime(
            row.get("publishedDate") or row.get("published_at") or row.get("date")
        ),
        tickers=tuple(tickers),
        jurisdiction="US" if tickers else None,
        event_type=event_type,
        raw_payload=row,
    )


def _ngn_item(
    row: dict[str, Any], *, ticker: str | None, event_type: str
) -> ProviderNewsItem:
    symbol = (
        _string(row.get("symbol") or row.get("ticker") or row.get("company_symbol"))
        or ticker
    )
    normalized = normalize_ticker(symbol or "", "NG") if symbol else ""
    source = _string(row.get("source") or row.get("publisher") or row.get("source_name"))
    published = _parse_datetime(
        row.get("published_at")
        or row.get("publishedDate")
        or row.get("date")
        or row.get("submitted_at")
        or row.get("filing_date")
    )
    url = _string(
        row.get("url") or row.get("link") or row.get("document_url") or row.get("pdf_url")
    )
    title = _string(row.get("title") or row.get("headline") or row.get("description"))
    return ProviderNewsItem(
        provider="ngnmarket",
        provider_id=str(row.get("id") or url or _fallback_id("ngnmarket", row)),
        title=title or "Untitled NGX item",
        url=url,
        summary=_string(
            row.get("summary") or row.get("snippet") or row.get("description")
        ),
        source_name=source or "NGN Market",
        published_at=published,
        tickers=tuple([normalized] if normalized else []),
        jurisdiction="NG",
        event_type=event_type,
        raw_payload=row,
    )


def _list_payload(payload: object) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "body", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _ngn_rows(payload: object) -> list[dict]:
    rows = _list_payload(payload)
    if rows:
        return [row for row in rows if isinstance(row, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("data", "items", "results", "disclosures", "news"):
                inner = data.get(key)
                if isinstance(inner, list):
                    return [row for row in inner if isinstance(row, dict)]
    return []


def _tickers(value: object) -> list[str]:
    raw: list[object]
    if isinstance(value, str):
        raw = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    tickers: list[str] = []
    for item in raw:
        ticker = str(item or "").strip().upper()
        if not ticker:
            continue
        if ticker not in tickers:
            tickers.append(ticker)
    return tickers


def _parse_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _aware_utc(value)
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware_utc(parsed)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fallback_id(provider: str, row: dict[str, Any]) -> str:
    raw = "|".join(
        [
            provider,
            str(row.get("url") or row.get("link") or ""),
            str(row.get("title") or row.get("headline") or ""),
            str(
                row.get("publishedDate")
                or row.get("published_at")
                or row.get("date")
                or ""
            ),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
