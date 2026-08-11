"""FX rate fetching for the live price platform.

Primary source: open.er-api.com (free, no key required).
Rate convention: NGN per 1 USD (e.g. 1363.18).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.core.market_constants import QUOTE_HTTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

ER_API_URL = "https://open.er-api.com/v6/latest/USD"


@dataclass(frozen=True)
class LiveFxRate:
    base_currency: str
    quote_currency: str
    rate: Decimal
    source: str
    as_of: datetime
    raw_payload: dict | None = None


async def fetch_usd_ngn_rate() -> LiveFxRate | None:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(QUOTE_HTTP_TIMEOUT_SECONDS)) as client:
            response = await client.get(ER_API_URL)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("fx_rate_fetch_failed", extra={"error": str(exc)})
        return None

    if not isinstance(payload, dict):
        return None

    ngn_rate = _decimal((payload.get("rates") or {}).get("NGN"))
    if ngn_rate is None or ngn_rate <= 0:
        logger.warning("fx_rate_missing_ngn")
        return None

    as_of = datetime.now(timezone.utc)
    time_last_updated = payload.get("time_last_update_unix")
    if time_last_updated:
        try:
            as_of = datetime.fromtimestamp(int(time_last_updated), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass

    return LiveFxRate(
        base_currency="USD",
        quote_currency="NGN",
        rate=ngn_rate,
        source="er-api",
        as_of=as_of,
        raw_payload=payload,
    )


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
