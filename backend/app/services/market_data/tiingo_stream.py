"""Tiingo WebSocket ingestion into the internal market snapshot cache.

The stream is the primary path for fresh US equity and FX marks when enabled.
It still writes to the existing instrument_quotes and fx_rates tables so the
rest of the app does not care whether data arrived through WebSocket or REST.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import certifi
import websockets
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.market_data.fx_provider import LiveFxRate
from app.services.market_data.fx_refresh import persist_fx_rate
from app.services.market_data.ingestion import persist_quotes
from app.services.market_data.mark_to_market import MarkResult, mark_open_positions
from app.services.market_data.quote_provider import LiveQuote
from app.services.market_data.sessions import JURISDICTION_US, is_market_open
from app.services.market_data.universe import build_price_universe
from app.services.realtime.events import (
    fx_rate_updated_event,
    portfolio_marked_event,
    quote_batch_updated_event,
)
from app.services.realtime.redis_bus import publish_event

logger = logging.getLogger(__name__)


@dataclass
class StreamFlushResult:
    quote_count: int = 0
    fx_count: int = 0
    mark_result: MarkResult = field(default_factory=MarkResult)


@dataclass
class ReconnectBackoff:
    seconds: int = field(default_factory=lambda: settings.tiingo_stream_reconnect_seconds)

    def reset(self) -> None:
        self.seconds = settings.tiingo_stream_reconnect_seconds

    async def sleep(self) -> None:
        delay = self.seconds
        self.seconds = min(
            self.seconds * 2,
            settings.tiingo_stream_reconnect_max_seconds,
        )
        await asyncio.sleep(delay)


def build_subscribe_message(
    *,
    token: str,
    threshold_level: int,
    tickers: list[str],
) -> str:
    """Build Tiingo's subscribe payload without logging the token."""
    return json.dumps(
        {
            "eventName": "subscribe",
            "authorization": token,
            "eventData": {
                "authToken": token,
                "thresholdLevel": threshold_level,
                "tickers": [ticker.lower() for ticker in tickers],
            },
        }
    )


def parse_iex_reference_message(
    payload: str | dict[str, Any],
    *,
    received_at: datetime | None = None,
) -> LiveQuote | None:
    """Parse Tiingo IEX thresholdLevel 6 reference-price messages.

    Official shape: {"service": "iex", "messageType": "A",
    "data": [timestamp, ticker, reference_price]}.
    """
    message = _message(payload)
    if not message or message.get("service") != "iex" or message.get("messageType") != "A":
        return None

    data = message.get("data")
    if not isinstance(data, list) or len(data) < 3:
        return None

    ticker = str(data[1] or "").upper()
    price = _decimal(data[2])
    if not ticker or price is None or price <= 0:
        return None

    received = _utc(received_at)
    as_of = _iso_datetime(data[0]) or received
    return LiveQuote(
        ticker=ticker,
        price=price,
        source="tiingo_stream",
        as_of=as_of,
        raw_payload={
            "provider": "tiingo",
            "stream": "iex",
            "threshold_level": 6,
            "provider_timestamp": as_of.isoformat(),
            "received_at": received.isoformat(),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "stream_status": "live",
            "message": _redact_token(message),
        },
    )


def parse_fx_message(
    payload: str | dict[str, Any],
    *,
    received_at: datetime | None = None,
) -> LiveFxRate | None:
    """Parse Tiingo FX top-of-book messages into a mid-price rate."""
    message = _message(payload)
    if not message or message.get("service") != "fx" or message.get("messageType") != "A":
        return None

    data = message.get("data")
    if not isinstance(data, list) or len(data) < 6:
        return None

    pair = str(data[1] or "").lower().replace("/", "")
    if len(pair) != 6:
        return None

    rate = _decimal(data[5]) or _decimal(data[4]) or _decimal(data[6])
    if rate is None or rate <= 0:
        return None

    received = _utc(received_at)
    as_of = _iso_datetime(data[2]) or received
    return LiveFxRate(
        base_currency=pair[:3].upper(),
        quote_currency=pair[3:].upper(),
        rate=rate,
        source="tiingo_stream",
        as_of=as_of,
        raw_payload={
            "provider": "tiingo",
            "stream": "fx",
            "threshold_level": settings.tiingo_fx_threshold_level,
            "provider_timestamp": as_of.isoformat(),
            "received_at": received.isoformat(),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "stream_status": "live",
            "message": _redact_token(message),
        },
    )


async def run_tiingo_streams(
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> None:
    """Run enabled Tiingo streams until cancelled."""
    if not settings.tiingo_stream_enabled:
        logger.info("tiingo_stream_disabled")
        return

    tasks = [run_equity_stream(session_factory=session_factory)]
    if settings.tiingo_fx_stream_enabled:
        tasks.append(run_fx_stream(session_factory=session_factory))
    else:
        logger.info("tiingo_fx_stream_disabled")

    await asyncio.gather(*tasks)


async def run_equity_stream(
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    connect: Callable[..., Any] = websockets.connect,
) -> None:
    """Maintain the Tiingo IEX reference-price stream for US quote symbols."""
    token = settings.hf_tiingo_api_key
    if not token:
        logger.info("tiingo_equity_stream_skipped_missing_key")
        return

    backoff = ReconnectBackoff()
    while True:
        if settings.hf_tiingo_stream_market_hours_only and not is_market_open(
            JURISDICTION_US
        ):
            await asyncio.sleep(max(settings.tiingo_stream_reconnect_seconds, 60))
            continue

        async with session_factory() as session:
            universe = await build_price_universe(session)
        us_universe = {
            ticker: ids
            for ticker, ids in universe.items()
            if not ticker.upper().endswith(".NG")
        }
        if settings.tiingo_stream_max_tickers:
            allowed = sorted(us_universe)[: settings.tiingo_stream_max_tickers]
            us_universe = {ticker: us_universe[ticker] for ticker in allowed}

        tickers = sorted(us_universe)
        if not tickers:
            await asyncio.sleep(max(settings.tiingo_stream_reconnect_seconds, 60))
            continue

        try:
            await _run_equity_subscription(
                connect=connect,
                token=token,
                tickers=tickers,
                universe=us_universe,
                session_factory=session_factory,
            )
            backoff.reset()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reconnect loop
            logger.warning(
                "tiingo_equity_stream_reconnecting delay_seconds=%s error=%s",
                backoff.seconds,
                exc,
            )
            await backoff.sleep()


async def run_fx_stream(
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    connect: Callable[..., Any] = websockets.connect,
) -> None:
    """Maintain the Tiingo FX stream for configured pairs."""
    token = settings.hf_tiingo_api_key
    if not token:
        logger.info("tiingo_fx_stream_skipped_missing_key")
        return

    pairs = list(settings.tiingo_fx_pairs)
    if not pairs:
        return

    backoff = ReconnectBackoff()
    while True:
        try:
            await _run_fx_subscription(
                connect=connect,
                token=token,
                pairs=pairs,
                session_factory=session_factory,
            )
            backoff.reset()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reconnect loop
            logger.warning(
                "tiingo_fx_stream_reconnecting delay_seconds=%s error=%s",
                backoff.seconds,
                exc,
            )
            await backoff.sleep()


async def _run_equity_subscription(
    *,
    connect: Callable[..., Any],
    token: str,
    tickers: list[str],
    universe: dict[str, list[Any]],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    logger.info("tiingo_equity_stream_connecting ticker_count=%s", len(tickers))
    buffer: dict[str, LiveQuote] = {}
    started_at = datetime.now(timezone.utc)

    async with connect(
        settings.tiingo_equity_stream_url,
        ssl=_tiingo_ssl_context(),
    ) as websocket:
        await websocket.send(
            build_subscribe_message(
                token=token,
                threshold_level=settings.tiingo_equity_threshold_level,
                tickers=tickers,
            )
        )
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=settings.tiingo_stream_flush_seconds,
                )
            except TimeoutError:
                await _flush_quotes(session_factory, universe, buffer)
                buffer.clear()
            else:
                quote = parse_iex_reference_message(raw)
                if quote is not None and quote.ticker in universe:
                    buffer[quote.ticker] = quote

            if (
                datetime.now(timezone.utc) - started_at
            ).total_seconds() >= settings.tiingo_stream_subscription_refresh_seconds:
                await _flush_quotes(session_factory, universe, buffer)
                return


async def _run_fx_subscription(
    *,
    connect: Callable[..., Any],
    token: str,
    pairs: list[str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    logger.info("tiingo_fx_stream_connecting pair_count=%s", len(pairs))
    buffer: dict[tuple[str, str], LiveFxRate] = {}

    async with connect(
        settings.tiingo_fx_stream_url,
        ssl=_tiingo_ssl_context(),
    ) as websocket:
        await websocket.send(
            build_subscribe_message(
                token=token,
                threshold_level=settings.tiingo_fx_threshold_level,
                tickers=pairs,
            )
        )
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=settings.tiingo_stream_flush_seconds,
                )
            except TimeoutError:
                await _flush_fx_rates(session_factory, buffer)
                buffer.clear()
            else:
                rate = parse_fx_message(raw)
                if rate is not None:
                    buffer[(rate.base_currency, rate.quote_currency)] = rate


async def _flush_quotes(
    session_factory: async_sessionmaker[AsyncSession],
    universe: dict[str, list[Any]],
    buffer: dict[str, LiveQuote],
) -> StreamFlushResult:
    if not buffer:
        return StreamFlushResult()

    async with session_factory() as session:
        await persist_quotes(session, universe, dict(buffer))
        mark_result = await mark_open_positions(session)
        await session.commit()

    await publish_event(
        quote_batch_updated_event(
            quotes=[
                {
                    "ticker": quote.ticker,
                    "price": str(quote.price),
                    "change_pct": str(quote.change_pct)
                    if quote.change_pct is not None
                    else None,
                    "currency": quote.currency,
                    "source": quote.source,
                    "as_of": quote.as_of.isoformat(),
                }
                for quote in buffer.values()
            ],
            as_of=datetime.now(timezone.utc).isoformat(),
        )
    )
    for portfolio in mark_result.portfolios:
        await publish_event(
            portfolio_marked_event(
                owner_user_id=portfolio.owner_user_id,
                portfolio_id=str(portfolio.portfolio_id),
                nav=str(portfolio.nav),
                cash_balance=str(portfolio.cash_balance),
                invested_value=str(portfolio.invested_value),
                position_count=portfolio.position_count,
            )
        )

    logger.info("tiingo_equity_stream_flushed", extra={"quote_count": len(buffer)})
    return StreamFlushResult(quote_count=len(buffer), mark_result=mark_result)


async def _flush_fx_rates(
    session_factory: async_sessionmaker[AsyncSession],
    buffer: dict[tuple[str, str], LiveFxRate],
) -> StreamFlushResult:
    if not buffer:
        return StreamFlushResult()

    async with session_factory() as session:
        for rate in buffer.values():
            await persist_fx_rate(session, rate)
        await session.commit()

    for rate in buffer.values():
        await publish_event(
            fx_rate_updated_event(
                base_currency=rate.base_currency,
                quote_currency=rate.quote_currency,
                rate=str(rate.rate),
                source=rate.source,
                as_of=rate.as_of.isoformat(),
            )
        )

    logger.info("tiingo_fx_stream_flushed", extra={"rate_count": len(buffer)})
    return StreamFlushResult(fx_count=len(buffer))


def _message(payload: str | dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return payload
    try:
        message = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return None
    return message if isinstance(message, dict) else None


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _redact_token(message: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(message)
    if "authorization" in redacted:
        redacted["authorization"] = "[redacted]"
    event_data = redacted.get("eventData")
    if isinstance(event_data, dict) and "authToken" in event_data:
        redacted["eventData"] = {**event_data, "authToken": "[redacted]"}
    return redacted


def _tiingo_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())
