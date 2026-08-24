from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.core.market_constants import (
    RADAR_POSITION_FLAG_CHANGE_PCT,
    RADAR_POSITION_FLAG_PRICE_Z,
    RADAR_POSITION_FLAG_SCORE,
    RADAR_POSITION_FLAG_VOLUME_RATIO,
    RADAR_SCAN_DELTA_CHANGE_POINTS,
    RADAR_SCAN_DELTA_PRICE_PCT,
    RADAR_UNIVERSE_FLAG_CHANGE_PCT,
    RADAR_UNIVERSE_FLAG_SCORE,
    RADAR_UNIVERSE_FLAG_VOLUME_RATIO,
    RADAR_WATCHLIST_FLAG_CHANGE_PCT,
    RADAR_WATCHLIST_FLAG_PRICE_Z,
    RADAR_WATCHLIST_FLAG_SCORE,
    RADAR_WATCHLIST_FLAG_VOLUME_RATIO,
)

CareTier = Literal["position", "watchlist", "queue", "universe"]


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
    on_watchlist: bool = False
    pinned_prior: bool = False
    in_portfolio: bool = False
    in_opportunity_queue: bool = False
    radar_priority: str | None = None
    priority_score: Decimal = Decimal("0")
    dimension_scores: dict[str, int] = field(default_factory=dict)
    priority_reasons: list[str] = field(default_factory=list)
    should_auto_promote: bool = False
    related_tickers: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    sparkline: list[dict[str, Any]] = field(default_factory=list)
    care_tier: CareTier = "universe"


@dataclass(frozen=True)
class CareThresholds:
    score: Decimal
    change_pct: Decimal
    volume_ratio: Decimal
    price_z: Decimal | None = None


_UNIVERSE_THRESHOLDS = CareThresholds(
    score=Decimal(str(RADAR_UNIVERSE_FLAG_SCORE)),
    change_pct=Decimal(str(RADAR_UNIVERSE_FLAG_CHANGE_PCT)),
    volume_ratio=Decimal(str(RADAR_UNIVERSE_FLAG_VOLUME_RATIO)),
)
_WATCHLIST_THRESHOLDS = CareThresholds(
    score=Decimal(str(RADAR_WATCHLIST_FLAG_SCORE)),
    change_pct=Decimal(str(RADAR_WATCHLIST_FLAG_CHANGE_PCT)),
    volume_ratio=Decimal(str(RADAR_WATCHLIST_FLAG_VOLUME_RATIO)),
    price_z=Decimal(str(RADAR_WATCHLIST_FLAG_PRICE_Z)),
)
_POSITION_THRESHOLDS = CareThresholds(
    score=Decimal(str(RADAR_POSITION_FLAG_SCORE)),
    change_pct=Decimal(str(RADAR_POSITION_FLAG_CHANGE_PCT)),
    volume_ratio=Decimal(str(RADAR_POSITION_FLAG_VOLUME_RATIO)),
    price_z=Decimal(str(RADAR_POSITION_FLAG_PRICE_Z)),
)


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

    price_z = abs(
        _evidence_decimal(candidate, "price_return_zscore")
        or _evidence_decimal(candidate, "price_return_zscore")
        or Decimal("0")
    )
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

    volume_z = _evidence_decimal(candidate, "volume_zscore") or _evidence_decimal(
        candidate, "volume_zscore"
    )
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

    candidate.care_tier = care_tier(candidate)
    candidate.evidence["care_tier"] = candidate.care_tier
    score += _apply_care_tier_flags(candidate, flags, change, price_z)

    scan_delta = abs(_evidence_decimal(candidate, "scan_delta_change_pct") or Decimal("0"))
    scan_price = abs(_evidence_decimal(candidate, "scan_delta_price_pct") or Decimal("0"))
    if scan_delta >= Decimal(str(RADAR_SCAN_DELTA_CHANGE_POINTS)) or scan_price >= Decimal(
        str(RADAR_SCAN_DELTA_PRICE_PCT)
    ):
        flags.append("scan_lurch")
        score += min(max(scan_delta, scan_price), Decimal("15"))

    merged: list[str] = []
    for flag in flags + inherited:
        if flag not in merged:
            merged.append(flag)
    candidate.flags = merged
    candidate.anomaly_score = score.quantize(Decimal("0.01"))
    return candidate


def care_tier(candidate: RadarCandidate) -> CareTier:
    """Live positions first, then watchlist, then open queue names, then the universe.

    Pulse ETFs are always_watched for coverage, not because the desk owns them.
    They stay on the universe bar.
    """
    if candidate.in_portfolio:
        return "position"
    if candidate.on_watchlist:
        return "watchlist"
    if candidate.in_opportunity_queue:
        return "queue"
    return "universe"


def thresholds_for(tier: CareTier) -> CareThresholds:
    if tier == "position":
        return _POSITION_THRESHOLDS
    if tier in {"watchlist", "queue"}:
        return _WATCHLIST_THRESHOLDS
    return _UNIVERSE_THRESHOLDS


def is_flagged(candidate: RadarCandidate) -> bool:
    if "scan_lurch" in candidate.flags:
        return True
    thresholds = thresholds_for(care_tier(candidate))
    if candidate.anomaly_score >= thresholds.score:
        return True
    if (
        candidate.volume_ratio is not None
        and candidate.volume_ratio >= thresholds.volume_ratio
    ):
        return True
    if (
        candidate.change_pct is not None
        and abs(candidate.change_pct) >= thresholds.change_pct
    ):
        return True
    if thresholds.price_z is not None:
        price_z = abs(_evidence_decimal(candidate, "price_return_zscore") or Decimal("0"))
        if price_z >= thresholds.price_z:
            return True
    return False


def _apply_care_tier_flags(
    candidate: RadarCandidate,
    flags: list[str],
    change: Decimal,
    price_z: Decimal,
) -> Decimal:
    """Tag holdings and watchlist names earlier. Do not treat pulse ETFs as watched."""
    tier = candidate.care_tier
    if tier == "universe":
        return Decimal("0")
    thresholds = thresholds_for(tier)
    volume_hit = (
        candidate.volume_ratio is not None
        and candidate.volume_ratio >= thresholds.volume_ratio
    )
    z_hit = thresholds.price_z is not None and price_z >= thresholds.price_z
    if tier == "position":
        if (
            candidate.change_pct is not None
            and candidate.change_pct <= -thresholds.change_pct
        ):
            flags.append("position_risk")
            return Decimal("4")
        if change >= thresholds.change_pct or volume_hit or z_hit:
            flags.append("position_move")
        return Decimal("0")
    if change >= thresholds.change_pct or volume_hit or z_hit:
        flags.append("watched_move")
    return Decimal("0")


def _evidence_decimal(candidate: RadarCandidate, key: str) -> Decimal | None:
    value = candidate.evidence.get(key)
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
