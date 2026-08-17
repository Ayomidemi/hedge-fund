"""Vendor calls for radar discovery. Jurisdiction is decided by the caller;
this module never mixes US and NGX endpoints in one function."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import httpx

from app.core.config import settings
from app.core.market_constants import (
    QUOTE_HTTP_TIMEOUT_SECONDS,
    RADAR_MOVER_LIST_LIMIT,
    RADAR_NG_DISCOVERY_LIMIT,
)
from app.services.market_radar.scoring import RadarCandidate

logger = logging.getLogger(__name__)

FMP_MOVER_ENDPOINTS = (
    ("/stable/most-actives", "unusual_volume"),
    ("/stable/biggest-gainers", "price_move"),
    ("/stable/biggest-losers", "risk_drop"),
)


async def fetch_us_movers() -> tuple[list[RadarCandidate], int, list[str]]:
    """Three FMP list endpoints. Returns (candidates, http_calls, errors)."""
    if not settings.hf_fmp_api_key:
        return [], 0, ["FMP API key is missing; US discovery skipped."]

    candidates: dict[str, RadarCandidate] = {}
    errors: list[str] = []
    calls = 0
    base_url = settings.fmp_base_url.removesuffix("/api")

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
    ) as client:
        for path, default_flag in FMP_MOVER_ENDPOINTS:
            calls += 1
            try:
                response = await client.get(
                    path, params={"apikey": settings.hf_fmp_api_key}
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"FMP {path} failed: {exc}")
                logger.warning("radar_fmp_movers_failed", extra={"path": path, "error": str(exc)})
                continue

            rows = _list_payload(payload)
            for item in rows[:RADAR_MOVER_LIST_LIMIT]:
                if not isinstance(item, dict):
                    continue
                ticker = str(item.get("symbol") or item.get("ticker") or "").upper()
                if not ticker or ticker.endswith(".NG"):
                    continue
                existing = candidates.get(ticker)
                change_pct = _decimal(
                    item.get("changesPercentage") or item.get("changePercentage")
                )
                candidate = existing or RadarCandidate(
                    ticker=ticker,
                    name=str(item.get("name") or ticker),
                    jurisdiction="US",
                    sector=str(item.get("sector") or "") or None,
                    industry=str(item.get("industry") or "") or None,
                    asset_class="etf" if ticker.startswith("XL") else "equity",
                    exchange="US",
                    currency="USD",
                    source="fmp",
                )
                candidate.price = _decimal(item.get("price")) or candidate.price
                candidate.change_pct = change_pct if change_pct is not None else candidate.change_pct
                candidate.volume = _int(item.get("volume")) or candidate.volume
                candidate.avg_volume = (
                    _int(item.get("avgVolume") or item.get("averageVolume"))
                    or candidate.avg_volume
                )
                if default_flag not in candidate.flags:
                    candidate.flags.append(default_flag)
                candidates[ticker] = candidate

    return list(candidates.values()), calls, errors


async def fetch_ngn_discovery() -> tuple[list[RadarCandidate], int, list[str]]:
    """At most two NGN Market list calls. Never per-symbol search."""
    if not settings.hf_ngnmarket_api_key:
        return [], 0, ["NGN Market API key is missing; NGX discovery skipped."]

    errors: list[str] = []
    calls = 0
    candidates: dict[str, RadarCandidate] = {}

    async with httpx.AsyncClient(
        base_url=settings.ngnmarket_base_url,
        timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS),
        headers={"Authorization": f"Bearer {settings.hf_ngnmarket_api_key}"},
    ) as client:
        for path, params in (("/companies", {"limit": "40"}), ("/etfs", {})):
            calls += 1
            try:
                response = await client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"NGN {path} failed: {exc}")
                logger.warning("radar_ngn_list_failed", extra={"path": path, "error": str(exc)})
                continue

            for item in _ngn_rows(payload)[:RADAR_NG_DISCOVERY_LIMIT]:
                symbol = str(item.get("symbol") or item.get("ticker") or "").upper()
                if not symbol:
                    continue
                ticker = symbol if symbol.endswith(".NG") else f"{symbol}.NG"
                price = _decimal(item.get("price"))
                previous_close = _decimal(item.get("prev_close") or item.get("previous_close"))
                change_pct = _decimal(item.get("change_pct") or item.get("changePercent"))
                if change_pct is None and price and previous_close and previous_close > 0:
                    change_pct = ((price - previous_close) / previous_close * 100).quantize(
                        Decimal("0.01")
                    )
                candidates[ticker] = RadarCandidate(
                    ticker=ticker,
                    name=str(item.get("name") or item.get("company_name") or symbol),
                    jurisdiction="NG",
                    sector=str(item.get("sector") or item.get("industry") or "") or None,
                    industry=str(item.get("industry") or "") or None,
                    asset_class="etf" if path == "/etfs" else "equity",
                    exchange="NGX",
                    currency="NGN",
                    source="ngnmarket",
                    price=price,
                    previous_close=previous_close,
                    change_pct=change_pct,
                    volume=_int(item.get("volume")),
                )

    ranked = sorted(
        candidates.values(),
        key=lambda item: abs(item.change_pct or Decimal("0")),
        reverse=True,
    )
    return ranked[:RADAR_NG_DISCOVERY_LIMIT], calls, errors


def _list_payload(payload: object) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "body"):
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
            inner = data.get("data")
            if isinstance(inner, list):
                return [row for row in inner if isinstance(row, dict)]
    return []


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace("%", ""))
    except (InvalidOperation, ValueError):
        return None


def _int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
