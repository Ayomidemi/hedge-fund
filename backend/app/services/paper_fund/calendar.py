"""Verified NYSE core sessions, including DST, holidays and early closes.

Source: https://www.nyse.com/trade/hours-calendars (2026–2028).
Fail closed outside the published calendar; refresh this table each year.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
HOLIDAYS = {
    2026: {"01-01", "01-19", "02-16", "04-03", "05-25", "06-19", "07-03", "09-07", "11-26", "12-25"},
    2027: {"01-01", "01-18", "02-15", "03-26", "05-31", "06-18", "07-05", "09-06", "11-25", "12-24"},
    2028: {"01-17", "02-21", "04-14", "05-29", "06-19", "07-04", "09-04", "11-23", "12-25"},
}
EARLY_CLOSES = {2026: {"11-27", "12-24"}, 2027: {"11-26"}, 2028: {"07-03", "11-24"}}


def market_blocker(now: datetime) -> str | None:
    local = now.astimezone(NEW_YORK)
    if local.year not in HOLIDAYS:
        return "NYSE calendar requires an update before this year can be traded."
    day = local.strftime("%m-%d")
    if local.weekday() >= 5 or day in HOLIDAYS[local.year]:
        return "US market is closed (weekend or exchange holiday)."
    close = time(13) if day in EARLY_CLOSES[local.year] else time(16)
    if not time(9, 30) <= local.time() < close:
        return "Waiting for the US regular trading session."
    return None


def session_bounds(now: datetime) -> tuple[datetime, datetime] | None:
    local = now.astimezone(NEW_YORK)
    if local.year not in HOLIDAYS or local.weekday() >= 5 or local.strftime("%m-%d") in HOLIDAYS[local.year]:
        return None
    close = time(13) if local.strftime("%m-%d") in EARLY_CLOSES[local.year] else time(16)
    return (datetime.combine(local.date(), time(9, 30), NEW_YORK),
            datetime.combine(local.date(), close, NEW_YORK))
