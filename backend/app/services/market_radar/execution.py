"""Execution eligibility for the long-only USD paper experiment.

Radar priority measures unusual activity, not expected profit. A positive,
confirmed signal and a verifiable current quote are prerequisites; the paper
engine must still enforce capital, position, session, and order limits.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.core.market_constants import RADAR_PULSE_TICKERS
from app.models import InstrumentQuote, RadarSnapshot
from app.services.market_data.quote_provider import _epoch_datetime, _iso_datetime

MAX_QUOTE_AGE_SECONDS = 120
MAX_SIGNAL_AGE_SECONDS = 900
MIN_AVERAGE_DOLLAR_VOLUME = Decimal("500000")
MIN_SHARE_PRICE = Decimal("5")


def quote_rejection(quote: InstrumentQuote | None, now: datetime) -> str | None:
    """Reject unverifiable marks, including old discovery rows labeled live."""
    if quote is None:
        return "A current executable quote is unavailable."
    if quote.is_stale:
        return "The quote is marked stale."
    if str(quote.currency).upper() != "USD":
        return "The paper fund requires USD quotes."
    price = _number(quote.price)
    if price is None or price <= 0:
        return "The quote price must be positive and finite."
    payload = quote.raw_payload if isinstance(quote.raw_payload, dict) else {}
    if quote.source == "fmp":
        provider_time = _epoch_datetime(payload.get("timestamp"))
    elif quote.source == "tiingo":
        provider_time = _iso_datetime(payload.get("lastSaleTimestamp"))
    elif quote.source == "tiingo_reference":
        provider_time = _iso_datetime(payload.get("timestamp"))
        reference = _number(payload.get("tngoLast"))
        if reference is None or abs(reference - price) > Decimal("0.000001"):
            return "The reference price does not match its provider observation."
    elif quote.source == "tiingo_stream":
        message = payload.get("message")
        data = message.get("data") if isinstance(message, dict) else None
        provider_time = (
            _iso_datetime(data[0])
            if isinstance(data, list) and len(data) >= 3
            and message.get("service") == "iex" and message.get("messageType") == "A"
            else None
        )
    else:
        return "A live FMP or Tiingo quote is required; discovery and closing marks cannot fill orders."
    if provider_time is None:
        return "The quote has no verifiable provider timestamp."
    if not isinstance(quote.as_of, datetime):
        return "The quote timestamp is missing."
    if abs((_utc(provider_time) - _utc(quote.as_of)).total_seconds()) > 1:
        return "The quote timestamp does not match its provider timestamp."
    age = (_utc(now) - _utc(provider_time)).total_seconds()
    if age < 0:
        return "The quote timestamp is in the future."
    if age > MAX_QUOTE_AGE_SECONDS:
        return "The quote is older than 120 seconds."
    return None


def execution_rejection(
    snapshot: RadarSnapshot,
    quote: InstrumentQuote | None,
    now: datetime,
) -> str | None:
    """Return the first blocker, or None if a signal may be sized by the engine."""
    if (
        snapshot.jurisdiction != "US"
        or snapshot.currency != "USD"
        or snapshot.asset_class not in {"equity", "etf"}
    ):
        return "The paper experiment supports US equities and ETFs in USD."
    if snapshot.ticker.upper() in RADAR_PULSE_TICKERS:
        return "Market and sector pulse instruments remain radar observations."
    if snapshot.carried_forward or snapshot.stale_reason:
        return "The radar observation is carried forward or stale."
    for timestamp in (snapshot.as_of, snapshot.source_as_of):
        if not isinstance(timestamp, datetime):
            return "The radar signal is missing an observation timestamp."
        age = (_utc(now) - _utc(timestamp)).total_seconds()
        if age < 0 or age >= MAX_SIGNAL_AGE_SECONDS:
            return "The radar signal must be no more than 15 minutes old and not future dated."
    if snapshot.radar_priority not in {"P0", "P1"}:
        return "The radar signal is below the execution priority threshold."
    evidence = snapshot.evidence if isinstance(snapshot.evidence, dict) else {}
    if evidence.get("move_scope") == "market":
        return "A market-wide move is insufficient for an individual entry."
    change = _number(snapshot.change_pct)
    if change is None or change <= 0:
        return "A falling or directionless price is not a long entry signal."
    price_z = _number(evidence.get("price_return_zscore"))
    if change < Decimal("4") and (price_z is None or price_z < Decimal("2.5")):
        return "The positive price signal is not strong enough for execution."
    volume_ratio = _number(snapshot.volume_ratio)
    # Compute a ratio only from actual observed volume and a measured baseline.
    if volume_ratio is None:
        volume = _number(snapshot.volume)
        average_volume = _number(snapshot.avg_volume)
        if volume is not None and average_volume is not None and average_volume > 0:
            volume_ratio = volume / average_volume
    volume_z = _number(evidence.get("volume_zscore"))
    relative = _number(evidence.get("sector_relative_return_pct"))
    if not (
        (volume_ratio is not None and volume_ratio >= 2)
        or (volume_z is not None and volume_z >= 2)
        or (relative is not None and relative >= 3)
    ):
        return "Measured volume or positive sector-relative confirmation is missing."
    liquidity = _number(evidence.get("avg_dollar_volume"))
    if liquidity is None or liquidity < MIN_AVERAGE_DOLLAR_VOLUME:
        return "Measured average dollar volume must be at least $500,000."
    quote_error = quote_rejection(quote, now)
    if quote_error:
        return quote_error
    price = _number(quote.price)
    if price < MIN_SHARE_PRICE:
        return "The paper experiment requires a share price of at least $5."
    reference = _number(snapshot.price)
    if reference is None or reference <= 0:
        return "The radar reference price is invalid."
    if abs(price / reference - 1) > Decimal("0.02"):
        return "The executable quote moved over 2% from the radar signal; wait for a new scan."
    previous_close = _number(quote.previous_close)
    current_change = _number(quote.change_pct)
    if previous_close is not None and previous_close > 0:
        current_change = (price / previous_close - 1) * 100
    if current_change is not None and current_change <= 0:
        return "The current quote no longer confirms a positive session move."
    return None


def _number(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
