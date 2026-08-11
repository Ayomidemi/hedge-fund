"""Typed event envelopes published on the platform event bus.

Envelope shape (JSON over Redis pub/sub and WebSocket):
{
  "type": "quote.batch_updated",
  "emitted_at": "2026-08-11T10:35:00Z",
  "owner_user_id": null,          # null => broadcast to everyone
  "payload": { ... }
}
"""

from datetime import datetime, timezone
from typing import Any

EVENT_QUOTE_BATCH_UPDATED = "quote.batch_updated"
EVENT_PORTFOLIO_MARKED = "portfolio.marked"
EVENT_PRICE_REFRESH_COMPLETED = "price_refresh.completed"
EVENT_FX_RATE_UPDATED = "fx.rate_updated"
EVENT_SYSTEM_LOG_ENTRY = "system_log.entry"


def make_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "owner_user_id": owner_user_id,
        "payload": payload,
    }


def quote_batch_updated_event(
    quotes: list[dict[str, Any]], as_of: str
) -> dict[str, Any]:
    return make_event(
        EVENT_QUOTE_BATCH_UPDATED,
        {"quotes": quotes, "as_of": as_of},
    )


def portfolio_marked_event(
    *,
    owner_user_id: str,
    portfolio_id: str,
    nav: str,
    cash_balance: str,
    invested_value: str,
    position_count: int,
) -> dict[str, Any]:
    return make_event(
        EVENT_PORTFOLIO_MARKED,
        {
            "portfolio_id": portfolio_id,
            "nav": nav,
            "cash_balance": cash_balance,
            "invested_value": invested_value,
            "position_count": position_count,
        },
        owner_user_id=owner_user_id,
    )


def price_refresh_completed_event(
    *,
    run_id: str,
    ticker_count: int,
    success_count: int,
    failure_count: int,
    positions_marked: int,
    status: str,
) -> dict[str, Any]:
    return make_event(
        EVENT_PRICE_REFRESH_COMPLETED,
        {
            "run_id": run_id,
            "ticker_count": ticker_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "positions_marked": positions_marked,
            "status": status,
        },
    )


def fx_rate_updated_event(
    *,
    base_currency: str,
    quote_currency: str,
    rate: str,
    source: str,
    as_of: str,
) -> dict[str, Any]:
    return make_event(
        EVENT_FX_RATE_UPDATED,
        {
            "base_currency": base_currency,
            "quote_currency": quote_currency,
            "rate": rate,
            "source": source,
            "as_of": as_of,
            "pair_label": f"{base_currency}/{quote_currency}",
        },
    )


def system_log_entry_event(
    *,
    owner_user_id: str | None,
    level: str,
    category: str,
    event: str,
    message: str,
) -> dict[str, Any]:
    return make_event(
        EVENT_SYSTEM_LOG_ENTRY,
        {
            "level": level,
            "category": category,
            "event": event,
            "message": message,
        },
        owner_user_id=owner_user_id,
    )
