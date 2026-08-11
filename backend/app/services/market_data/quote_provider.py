"""Batch quote fetching with a provider fallback chain.

This module is the ONLY place allowed to call market data providers for live
prices. Everything else reads from the instrument_quotes table.

Chain (ordered by what free-tier plans actually allow):
1. Tiingo IEX     - true batch endpoint, one request per cycle
2. FMP /stable/quote - per-symbol fallback (free tier, ~250 calls/day)
3. Polygon prev-close - per-symbol last resort (previous day's close)

Nigerian tickers (SYMBOL.NG) are fetched from NGN Market's free search
endpoint individually.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.core.config import settings
from app.core.market_constants import PRICE_BATCH_SIZE, QUOTE_HTTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveQuote:
    ticker: str
    price: Decimal
    source: str
    as_of: datetime
    previous_close: Decimal | None = None
    change_pct: Decimal | None = None
    day_open: Decimal | None = None
    day_high: Decimal | None = None
    day_low: Decimal | None = None
    volume: int | None = None
    currency: str = "USD"
    raw_payload: dict | None = None


async def fetch_quotes(tickers: list[str]) -> dict[str, LiveQuote]:
    """Fetch latest quotes for the given tickers.

    Returns a mapping of ticker -> LiveQuote. Missing tickers simply won't be
    present in the result; callers decide how to treat them (stale flag).
    """
    ng_tickers = [ticker for ticker in tickers if ticker.upper().endswith(".NG")]
    us_tickers = [ticker for ticker in tickers if not ticker.upper().endswith(".NG")]

    quotes: dict[str, LiveQuote] = {}

    for batch in _batches(us_tickers, PRICE_BATCH_SIZE):
        remaining = list(batch)

        if remaining and settings.hf_tiingo_api_key:
            fetched = await _fetch_tiingo_iex(remaining)
            quotes.update(fetched)
            remaining = [ticker for ticker in remaining if ticker not in fetched]

        if remaining and settings.hf_fmp_api_key:
            fetched = await _fetch_fmp_quotes(remaining)
            quotes.update(fetched)
            remaining = [ticker for ticker in remaining if ticker not in fetched]

        if remaining and settings.hf_polygon_api_key:
            fetched = await _fetch_polygon_prev_close(remaining)
            quotes.update(fetched)
            remaining = [ticker for ticker in remaining if ticker not in fetched]

        if remaining:
            logger.warning(
                "quotes_missing_after_provider_chain",
                extra={"tickers": remaining},
            )

    if ng_tickers and settings.hf_ngnmarket_api_key:
        quotes.update(await _fetch_ngn_quotes(ng_tickers))

    return quotes


def _batches(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def _fetch_fmp_quotes(tickers: list[str]) -> dict[str, LiveQuote]:
    """FMP /stable/quote is per-symbol on the free tier, so this is used as
    a fallback for symbols the Tiingo batch missed - not for full batches."""
    base_url = settings.fmp_base_url.removesuffix("/api")
    now = datetime.now(timezone.utc)
    quotes: dict[str, LiveQuote] = {}
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
    ) as client:
        for ticker in tickers:
            try:
                response = await client.get(
                    "/stable/quote",
                    params={"symbol": ticker, "apikey": settings.hf_fmp_api_key},
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning(
                    "fmp_quote_failed",
                    extra={"ticker_symbol": ticker, "error": str(exc)},
                )
                continue

            item = payload[0] if isinstance(payload, list) and payload else None
            if not isinstance(item, dict):
                continue
            price = _decimal(item.get("price"))
            if price is None or price <= 0:
                continue
            quotes[ticker.upper()] = LiveQuote(
                ticker=ticker.upper(),
                price=price,
                source="fmp",
                as_of=_epoch_datetime(item.get("timestamp")) or now,
                previous_close=_decimal(item.get("previousClose")),
                change_pct=_decimal(item.get("changePercentage")),
                day_open=_decimal(item.get("open")),
                day_high=_decimal(item.get("dayHigh")),
                day_low=_decimal(item.get("dayLow")),
                volume=_int(item.get("volume")),
                raw_payload=item,
            )
    return quotes


async def _fetch_polygon_prev_close(tickers: list[str]) -> dict[str, LiveQuote]:
    """Polygon free tier only exposes previous-day aggregates; used as the
    last resort so a symbol at least gets yesterday's close as a mark."""
    quotes: dict[str, LiveQuote] = {}
    async with httpx.AsyncClient(
        base_url=settings.polygon_base_url,
        timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
        headers={"Authorization": f"Bearer {settings.hf_polygon_api_key}"},
    ) as client:
        for ticker in tickers:
            try:
                response = await client.get(f"/v2/aggs/ticker/{ticker}/prev")
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning(
                    "polygon_prev_close_failed",
                    extra={"ticker_symbol": ticker, "error": str(exc)},
                )
                continue

            results = payload.get("results") if isinstance(payload, dict) else None
            item = results[0] if isinstance(results, list) and results else None
            if not isinstance(item, dict):
                continue
            price = _decimal(item.get("c"))
            if price is None or price <= 0:
                continue
            quotes[ticker.upper()] = LiveQuote(
                ticker=ticker.upper(),
                price=price,
                source="polygon",
                as_of=_epoch_datetime(item.get("t")) or datetime.now(timezone.utc),
                day_open=_decimal(item.get("o")),
                day_high=_decimal(item.get("h")),
                day_low=_decimal(item.get("l")),
                volume=_int(item.get("v")),
                raw_payload=item,
            )
    return quotes


async def _fetch_tiingo_iex(tickers: list[str]) -> dict[str, LiveQuote]:
    try:
        async with httpx.AsyncClient(
            base_url=settings.tiingo_base_url,
            timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
            headers={"Authorization": f"Token {settings.hf_tiingo_api_key}"},
        ) as client:
            response = await client.get(
                "/iex/",
                params={"tickers": ",".join(ticker.lower() for ticker in tickers)},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("tiingo_iex_failed", extra={"error": str(exc)})
        return {}

    if not isinstance(payload, list):
        return {}

    now = datetime.now(timezone.utc)
    quotes: dict[str, LiveQuote] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").upper()
        price = (
            _decimal(item.get("last"))
            or _decimal(item.get("tngoLast"))
            or _decimal(item.get("mid"))
        )
        if not ticker or price is None or price <= 0:
            continue
        as_of = _iso_datetime(item.get("lastSaleTimestamp")) or now
        quotes[ticker] = LiveQuote(
            ticker=ticker,
            price=price,
            source="tiingo",
            as_of=as_of,
            previous_close=_decimal(item.get("prevClose")),
            day_open=_decimal(item.get("open")),
            day_high=_decimal(item.get("high")),
            day_low=_decimal(item.get("low")),
            volume=_int(item.get("volume")),
            raw_payload=item,
        )
    return quotes


async def _fetch_ngn_quotes(tickers: list[str]) -> dict[str, LiveQuote]:
    """NGN Market quotes via the companies search endpoint, which is
    available on the free plan and includes price / prev_close fields
    (unlike /companies/{symbol}, which requires a paid plan)."""
    quotes: dict[str, LiveQuote] = {}
    now = datetime.now(timezone.utc)
    async with httpx.AsyncClient(
        base_url=settings.ngnmarket_base_url,
        timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
        headers={"Authorization": f"Bearer {settings.hf_ngnmarket_api_key}"},
    ) as client:
        for ticker in tickers:
            symbol = ticker.upper().removesuffix(".NG")
            try:
                response = await client.get(
                    "/companies",
                    params={"search": symbol, "limit": "10"},
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning(
                    "ngn_quote_failed",
                    extra={"ticker_symbol": ticker, "error": str(exc)},
                )
                continue

            item = _ngn_company_match(payload, symbol)
            if item is None:
                continue
            price = _decimal(item.get("price")) or _decimal(item.get("prev_close"))
            if price is None or price <= 0:
                continue
            previous_close = _decimal(item.get("prev_close"))
            change_pct = None
            if previous_close and previous_close > 0:
                change_pct = ((price - previous_close) / previous_close * 100).quantize(
                    Decimal("0.0001")
                )
            quotes[ticker.upper()] = LiveQuote(
                ticker=ticker.upper(),
                price=price,
                source="ngnmarket",
                as_of=now,
                previous_close=previous_close,
                change_pct=change_pct,
                day_high=_decimal(item.get("day_high")),
                day_low=_decimal(item.get("day_low")),
                volume=_int(item.get("volume")),
                currency="NGN",
                raw_payload=item,
            )
    return quotes


def _ngn_company_match(payload: object, symbol: str) -> dict | None:
    """Extract the exact-symbol row from the NGN Market search response:
    {"success": true, "data": {"data": [{"symbol": ..., "price": ...}]}}"""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict):
        data = data.get("data")
    if not isinstance(data, list):
        return None
    for item in data:
        if (
            isinstance(item, dict)
            and str(item.get("symbol") or "").upper() == symbol
        ):
            return item
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _epoch_datetime(value: object, *, nanoseconds: bool = False) -> datetime | None:
    if value is None:
        return None
    try:
        timestamp = float(str(value))
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    if nanoseconds:
        timestamp /= 1_000_000_000
    elif timestamp > 1e12:  # milliseconds
        timestamp /= 1000
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _iso_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
