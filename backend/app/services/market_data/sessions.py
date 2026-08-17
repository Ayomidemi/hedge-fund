"""Jurisdiction-aware market session helpers.

Every quote and discovery call must be gated here so US vendors are never
hit for NGX names, NGX vendors are never hit for US names, and closed
sessions do not burn API quota.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

JURISDICTION_US = "US"
JURISDICTION_NG = "NG"
ALL_JURISDICTIONS = (JURISDICTION_US, JURISDICTION_NG)

# Approximate regular sessions in UTC. No holiday calendar; wide enough to
# cover DST for US and WAT (no DST) for NGX.
_US_OPEN = time(13, 30)
_US_CLOSE = time(21, 0)
_NG_OPEN = time(9, 0)  # 10:00 WAT
_NG_CLOSE = time(13, 30)  # 14:30 WAT


@dataclass(frozen=True)
class JurisdictionSession:
    jurisdiction: str
    is_open: bool
    in_post_close_window: bool
    label: str

    @property
    def allows_discovery(self) -> bool:
        return self.is_open or self.in_post_close_window

    @property
    def allows_live_quotes(self) -> bool:
        return self.is_open


def jurisdiction_for_ticker(ticker: str) -> str:
    return JURISDICTION_NG if ticker.upper().endswith(".NG") else JURISDICTION_US


def partition_tickers(tickers: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {JURISDICTION_US: [], JURISDICTION_NG: []}
    for ticker in tickers:
        grouped[jurisdiction_for_ticker(ticker)].append(ticker)
    return grouped


def is_market_open(jurisdiction: str, now: datetime | None = None) -> bool:
    return session_for(jurisdiction, now).is_open


def is_us_market_open(now: datetime | None = None) -> bool:
    return session_for(JURISDICTION_US, now).is_open


def is_ngx_market_open(now: datetime | None = None) -> bool:
    return session_for(JURISDICTION_NG, now).is_open


def session_for(
    jurisdiction: str,
    now: datetime | None = None,
    *,
    post_close_hours: int = 2,
) -> JurisdictionSession:
    now = _utc(now)
    if jurisdiction == JURISDICTION_NG:
        return _session(
            JURISDICTION_NG,
            now,
            _NG_OPEN,
            _NG_CLOSE,
            post_close_hours,
            open_label="NGX open",
            closed_label="NGX closed",
        )
    return _session(
        JURISDICTION_US,
        now,
        _US_OPEN,
        _US_CLOSE,
        post_close_hours,
        open_label="US open",
        closed_label="US closed",
    )


def sessions_now(
    now: datetime | None = None,
    *,
    post_close_hours: int = 2,
) -> dict[str, JurisdictionSession]:
    now = _utc(now)
    return {
        jurisdiction: session_for(jurisdiction, now, post_close_hours=post_close_hours)
        for jurisdiction in ALL_JURISDICTIONS
    }


def open_jurisdictions(
    now: datetime | None = None,
    *,
    include_post_close: bool = False,
    post_close_hours: int = 2,
) -> list[str]:
    now = _utc(now)
    result: list[str] = []
    for jurisdiction in ALL_JURISDICTIONS:
        state = session_for(
            jurisdiction, now, post_close_hours=post_close_hours
        )
        if state.is_open or (include_post_close and state.in_post_close_window):
            result.append(jurisdiction)
    return result


def _session(
    jurisdiction: str,
    now: datetime,
    open_time: time,
    close_time: time,
    post_close_hours: int,
    *,
    open_label: str,
    closed_label: str,
) -> JurisdictionSession:
    if now.weekday() >= 5:
        return JurisdictionSession(jurisdiction, False, False, closed_label)

    clock = now.time()
    is_open = open_time <= clock <= close_time
    in_post_close = False
    if not is_open:
        close_at = datetime.combine(now.date(), close_time, tzinfo=timezone.utc)
        in_post_close = close_at < now <= close_at + timedelta(hours=post_close_hours)

    if is_open:
        label = open_label
    elif in_post_close:
        label = f"{jurisdiction} post-close"
    else:
        label = closed_label
    return JurisdictionSession(jurisdiction, is_open, in_post_close, label)


def _utc(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
