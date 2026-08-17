from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass
class RadarCandidate:
    ticker: str
    name: str
    jurisdiction: str
    sector: str | None = None
    industry: str | None = None
    asset_class: str = "equity"
    exchange: str | None = None
    currency: str = "USD"
    source: str = ""
    always_watched: bool = False
    price: Decimal | None = None
    previous_close: Decimal | None = None
    change_pct: Decimal | None = None
    volume: int | None = None
    avg_volume: int | None = None
    volume_ratio: Decimal | None = None
    anomaly_score: Decimal = Decimal("0")
    flags: list[str] = field(default_factory=list)
    is_catalog_member: bool = False
    source_as_of: datetime | None = None
    carried_forward: bool = False
    stale_reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    sparkline: list[dict[str, Any]] = field(default_factory=list)


def score_candidate(candidate: RadarCandidate) -> RadarCandidate:
    """Score unusual-versus-itself and unusual-versus-sector-ETF.

    Vendor list membership may tag a row. It does not add score and does not
    by itself put the name in the Opportunity Queue.
    """
    flags: list[str] = []
    score = Decimal("0")
    change = abs(candidate.change_pct) if candidate.change_pct is not None else Decimal("0")
    inherited = [
        flag
        for flag in candidate.flags
        if flag in {"unusual_volume", "price_move", "risk_drop"}
    ]

    if candidate.avg_volume and candidate.avg_volume > 0 and candidate.volume:
        candidate.volume_ratio = (
            Decimal(candidate.volume) / Decimal(candidate.avg_volume)
        ).quantize(Decimal("0.01"))
    elif candidate.volume_ratio is None:
        candidate.volume_ratio = None

    price_z = abs(_evidence_decimal(candidate, "price_return_zscore") or Decimal("0"))
    if price_z >= Decimal("2"):
        flags.append("price_anomaly")
        score += min(price_z * Decimal("3"), Decimal("12"))
    elif change >= Decimal("5"):
        flags.append("price_move")
        score += min(change, Decimal("12"))

    if candidate.change_pct is not None and candidate.change_pct <= Decimal("-5"):
        flags.append("risk_drop")
        if "price_anomaly" not in flags and "price_move" not in flags:
            score += Decimal("5")

    volume_z = _evidence_decimal(candidate, "volume_zscore")
    if volume_z is not None and volume_z >= Decimal("2"):
        flags.append("volume_anomaly")
        score += min(volume_z * Decimal("2.5"), Decimal("12"))
    elif candidate.volume_ratio is not None and candidate.volume_ratio >= Decimal("2.5"):
        flags.append("unusual_volume")
        extra = (candidate.volume_ratio - Decimal("1")) * Decimal("5")
        score += min(extra, Decimal("15"))

    volatility_ratio = _evidence_decimal(candidate, "volatility_ratio")
    if volatility_ratio is not None and volatility_ratio >= Decimal("1.5"):
        flags.append("volatility_shift")
        score += min((volatility_ratio - Decimal("1")) * Decimal("6"), Decimal("10"))

    sector_relative = abs(
        _evidence_decimal(candidate, "sector_relative_return_pct") or Decimal("0")
    )
    if sector_relative >= Decimal("3"):
        flags.append("sector_relative_move")
        score += min(sector_relative * Decimal("1.5"), Decimal("9"))

    if candidate.always_watched and change >= Decimal("2"):
        flags.append("watched_move")

    merged: list[str] = []
    for flag in flags + inherited:
        if flag not in merged:
            merged.append(flag)
    candidate.flags = merged
    candidate.anomaly_score = score.quantize(Decimal("0.01"))
    return candidate


def is_flagged(candidate: RadarCandidate) -> bool:
    if candidate.anomaly_score >= Decimal("8"):
        return True
    if candidate.volume_ratio is not None and candidate.volume_ratio >= Decimal("2.5"):
        return True
    if candidate.change_pct is not None and abs(candidate.change_pct) >= Decimal("5"):
        return True
    return False


def _evidence_decimal(candidate: RadarCandidate, key: str) -> Decimal | None:
    value = candidate.evidence.get(key)
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
