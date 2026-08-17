from dataclasses import dataclass, field
from decimal import Decimal


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


def score_candidate(candidate: RadarCandidate) -> RadarCandidate:
    flags: list[str] = []
    score = Decimal("0")
    change = abs(candidate.change_pct) if candidate.change_pct is not None else Decimal("0")

    if candidate.avg_volume and candidate.avg_volume > 0 and candidate.volume:
        candidate.volume_ratio = (
            Decimal(candidate.volume) / Decimal(candidate.avg_volume)
        ).quantize(Decimal("0.01"))
    else:
        candidate.volume_ratio = None

    if change >= Decimal("3"):
        flags.append("price_move")
        score += min(change, Decimal("15"))
    if candidate.change_pct is not None and candidate.change_pct <= Decimal("-4"):
        flags.append("risk_drop")
        score += Decimal("5")
    if candidate.volume_ratio is not None and candidate.volume_ratio >= Decimal("2"):
        flags.append("unusual_volume")
        extra = (candidate.volume_ratio - Decimal("1")) * Decimal("5")
        score += min(extra, Decimal("20"))
    if candidate.always_watched and change >= Decimal("2"):
        flags.append("watched_move")
        score += Decimal("2")

    merged: list[str] = []
    for flag in flags + list(candidate.flags):
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
