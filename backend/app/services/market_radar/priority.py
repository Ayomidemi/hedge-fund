"""Radar priority tiers and Opportunity Queue evidence packages.

Anomaly scoring stays in scoring.py. This module decides whether a flagged
name is P0–P3, whether it may auto-enter the queue, and what evidence the
desk sees when it does.

P0  Position risk or an extraordinary tape event.
P1  Strong, confirmed anomaly on a name worth opening today.
P2  Interesting; keep on Radar, do not auto-promote.
P3  Background observation; store it, do not open it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from app.core.market_constants import (
    RADAR_AUTO_PROMOTE_PRIORITIES,
    RADAR_ILLIQUID_USD_DOLLAR_VOLUME,
    RADAR_MAX_P1_PROMOTIONS_PER_OWNER,
    RADAR_PULSE_TICKERS,
)
from app.services.market_radar.scoring import RadarCandidate, care_tier, is_flagged


QUEUE_PRIORITY = {"P0": "urgent", "P1": "high", "P2": "medium", "P3": "low"}
INDUSTRY_EVENT_RATIO = Decimal("0.40")
INDUSTRY_EVENT_MIN_FLAGGED = 3
MARKET_EVENT_INDUSTRY_SHARE = Decimal("0.45")
MARKET_EVENT_MIN_INDUSTRY_EVENTS = 2
MARKET_EVENT_NAME_RATIO = Decimal("0.30")
MARKET_EVENT_MIN_FLAGGED = 8
_WEIGHTS = {
    "price_anomaly": 0.28,
    "volume_anomaly": 0.22,
    "relative_move": 0.15,
    "industry_breadth": 0.10,
    "portfolio_relevance": 0.18,
    "watchlist_relevance": 0.07,
}


@dataclass(frozen=True)
class IndustryContext:
    key: str
    label: str
    jurisdiction: str
    member_count: int
    flagged_count: int
    flagged_ratio: Decimal
    median_change_pct: Decimal | None
    median_volume_ratio: Decimal | None = None
    declining_count: int = 0
    advancing_count: int = 0
    related_tickers: tuple[str, ...] = ()
    status: str = "quiet"


def assign_priorities(candidates: list[RadarCandidate]) -> None:
    contexts = build_industry_contexts(candidates)
    for candidate in candidates:
        assign_priority(candidate, contexts.get(_industry_key(candidate)))


def assign_priority(
    candidate: RadarCandidate,
    context: IndustryContext | None = None,
) -> RadarCandidate:
    dimensions = dimension_scores(candidate, context)
    candidate.dimension_scores = {
        key: value for key, value in dimensions.items() if value is not None
    }
    candidate.priority_score = _weighted_score(dimensions)
    candidate.radar_priority = None
    candidate.priority_reasons = []
    candidate.should_auto_promote = False
    related = context.related_tickers if context else ()
    candidate.related_tickers = [ticker for ticker in related if ticker != candidate.ticker]
    _write_industry_evidence(candidate, context)

    if not is_flagged(candidate):
        _write_priority_evidence(candidate)
        return candidate

    priority, reasons = _classify(candidate, dimensions, context)
    candidate.radar_priority = priority
    candidate.priority_reasons = reasons
    candidate.should_auto_promote = is_auto_promotable(candidate)
    _write_priority_evidence(candidate)
    return candidate


def is_auto_promotable(candidate: RadarCandidate) -> bool:
    if candidate.carried_forward:
        return False
    if candidate.radar_priority not in RADAR_AUTO_PROMOTE_PRIORITIES:
        return False
    if _is_pulse_instrument(candidate):
        return False
    # Market-wide tape floods the queue; keep those on Radar unless P0.
    if (
        candidate.radar_priority == "P1"
        and candidate.evidence.get("move_scope") == "market"
    ):
        return False
    if candidate.radar_priority == "P1" and not _has_strong_confirmation(candidate):
        return False
    return is_flagged(candidate)


def select_promotions(
    flagged: list[RadarCandidate],
    *,
    p1_limit: int = RADAR_MAX_P1_PROMOTIONS_PER_OWNER,
) -> list[RadarCandidate]:
    eligible = [item for item in flagged if is_auto_promotable(item)]
    p0 = [item for item in eligible if item.radar_priority == "P0"]
    p0.sort(key=lambda item: item.priority_score, reverse=True)
    p1 = [item for item in eligible if item.radar_priority == "P1"]
    p1.sort(key=lambda item: item.priority_score, reverse=True)
    return p0 + p1[: max(p1_limit, 0)]


def queue_priority_for(radar_priority: str | None) -> str:
    return QUEUE_PRIORITY.get(radar_priority or "", "medium")


def build_evidence_package(
    candidate: RadarCandidate,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    moment = as_of or datetime.now(timezone.utc)
    return {
        "source": "market_radar",
        "schema_version": 1,
        "ticker": candidate.ticker,
        "name": candidate.name,
        "jurisdiction": candidate.jurisdiction,
        "as_of": moment.isoformat(),
        "radar_priority": candidate.radar_priority,
        "queue_priority": queue_priority_for(candidate.radar_priority),
        "anomaly_score": str(candidate.anomaly_score),
        "priority_score": str(candidate.priority_score),
        "flags": list(candidate.flags),
        "reasons": list(candidate.priority_reasons),
        "dimensions": dict(candidate.dimension_scores),
        "facts": _facts(candidate),
        "context": {
            "care_tier": care_tier(candidate),
            "in_portfolio": candidate.in_portfolio,
            "in_opportunity_queue": candidate.in_opportunity_queue,
            "on_watchlist": candidate.on_watchlist,
            "always_watched": candidate.always_watched,
            "sector": candidate.sector,
            "industry": candidate.industry,
            "related_tickers": list(candidate.related_tickers),
            "industry_label": candidate.evidence.get("industry_label"),
            "industry_flagged_count": candidate.evidence.get("industry_flagged_count"),
            "industry_member_count": candidate.evidence.get("industry_member_count"),
            "industry_flagged_ratio": candidate.evidence.get("industry_flagged_ratio"),
        },
        "promotion_rule": _promotion_rule(candidate),
        "caveat": (
            "Historical association and unusual tape, not a trade authorization. "
            "Ticker Analyst still has to decide."
        ),
    }


def thesis_for(candidate: RadarCandidate) -> str:
    move = _signed_pct(candidate.change_pct)
    ratio = candidate.volume_ratio
    volume_text = f"{ratio}x volume" if ratio is not None else "volume unconfirmed"
    z_score = _price_z(candidate)
    z_text = f"; history z={z_score}" if z_score is not None else ""
    relative = _relative_pct(candidate)
    relative_text = ""
    if relative is not None:
        benchmark = candidate.evidence.get("sector_benchmark") or "sector"
        relative_text = f"; residual vs {benchmark} {relative}%"
    industry_text = ""
    industry = (
        candidate.evidence.get("industry_label") or candidate.industry or candidate.sector
    )
    if industry and candidate.evidence.get("industry_flagged_count"):
        industry_text = (
            f" {industry} tape: {candidate.evidence['industry_flagged_count']}/"
            f"{candidate.evidence.get('industry_member_count', '?')} names flagged."
        )
    reasons = "; ".join(candidate.priority_reasons) or "flagged by radar rules"
    related = ""
    if candidate.related_tickers:
        related = f" Related flagged names: {', '.join(candidate.related_tickers[:5])}."
    return (
        f"Market Radar {candidate.radar_priority or 'unranked'}: "
        f"{candidate.ticker} {move} on {volume_text}{z_text}{relative_text}. "
        f"{reasons}.{industry_text}{related} "
        "This is a discovery with evidence, not a position."
    )


def research_question_for(candidate: RadarCandidate) -> str:
    industry = candidate.industry or candidate.sector or "its group"
    if candidate.in_portfolio:
        return (
            f"Does the live {candidate.ticker} position still match the original thesis, "
            "or is this tape a risk event that should change size or exit?"
        )
    scope = candidate.evidence.get("move_scope")
    if scope == "industry":
        return (
            f"Is {candidate.ticker} just riding a {industry} move, "
            "or is there a company-specific reason to open it?"
        )
    if scope == "market":
        return (
            f"Is {candidate.ticker} a market-wide tape print, "
            "or a name that still deserves company-level work?"
        )
    if scope == "isolated":
        return (
            f"This looks company-specific versus {industry}. "
            "Does it survive Ticker Analyst quality, valuation and risk checks?"
        )
    return (
        f"Is {candidate.ticker}'s move company-specific or a {industry} event, "
        "and does it survive Ticker Analyst quality, valuation and risk checks?"
    )


def next_action_for(candidate: RadarCandidate) -> str:
    if candidate.radar_priority == "P0":
        return (
            f"Open Ticker Analyst for {candidate.ticker} immediately and check "
            "position risk before any other discovery work."
        )
    return (
        f"Open Ticker Analyst for {candidate.ticker} with this evidence package. "
        "Do not size a position from Radar."
    )


def build_industry_contexts(
    members: Sequence[Any],
) -> dict[str, IndustryContext]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for member in members:
        grouped[_industry_key(member)].append(member)

    draft: dict[str, IndustryContext] = {}
    for key, group in grouped.items():
        flagged = [item for item in group if _member_is_flagged(item)]
        changes = sorted(
            float(item.change_pct)
            for item in group
            if getattr(item, "change_pct", None) is not None
        )
        volumes = sorted(
            float(item.volume_ratio)
            for item in group
            if getattr(item, "volume_ratio", None) is not None
        )
        ratio = (
            (Decimal(len(flagged)) / Decimal(len(group))).quantize(Decimal("0.01"))
            if group
            else Decimal("0")
        )
        sample = group[0]
        jurisdictions = {
            str(getattr(item, "jurisdiction", "") or "") for item in group
        }
        draft[key] = IndustryContext(
            key=key,
            label=(
                getattr(sample, "industry", None)
                or getattr(sample, "sector", None)
                or "Unclassified"
            ),
            jurisdiction=(
                next(iter(jurisdictions))
                if len(jurisdictions) == 1
                else "mixed"
            ),
            member_count=len(group),
            flagged_count=len(flagged),
            flagged_ratio=ratio,
            median_change_pct=_median_decimal(changes),
            median_volume_ratio=_median_decimal(volumes),
            declining_count=sum(
                1
                for item in group
                if getattr(item, "change_pct", None) is not None
                and item.change_pct < 0
            ),
            advancing_count=sum(
                1
                for item in group
                if getattr(item, "change_pct", None) is not None
                and item.change_pct > 0
            ),
            related_tickers=tuple(
                getattr(item, "ticker")
                for item in sorted(
                    flagged,
                    key=lambda item: float(getattr(item, "anomaly_score", 0) or 0),
                    reverse=True,
                )
            ),
            status=_industry_status_without_market(len(flagged), len(group), ratio),
        )

    market_jurisdictions = _market_event_jurisdictions(draft, members)
    return {
        key: _with_status(
            context,
            "market_event"
            if context.jurisdiction in market_jurisdictions
            and _is_industry_event(context)
            else context.status,
        )
        for key, context in draft.items()
    }


def dimension_scores(
    candidate: RadarCandidate,
    context: IndustryContext | None,
) -> dict[str, int | None]:
    return {
        "price_anomaly": _price_dimension(candidate),
        "volume_anomaly": _volume_dimension(candidate),
        "relative_move": _relative_dimension(candidate),
        "industry_breadth": _industry_dimension(context),
        "portfolio_relevance": 100 if candidate.in_portfolio else None,
        "watchlist_relevance": _watchlist_dimension(candidate) or None,
    }


def _classify(
    candidate: RadarCandidate,
    dimensions: dict[str, int | None],
    context: IndustryContext | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    illiquid = _is_illiquid(candidate)
    confirmed = _has_confirmation(candidate)
    score = candidate.priority_score
    price_dim = dimensions.get("price_anomaly") or 0

    if candidate.in_portfolio and _is_portfolio_risk(candidate):
        reasons.append("Live position with a material adverse or unusual move")
        return "P0", reasons
    if (
        not _is_pulse_instrument(candidate)
        and candidate.anomaly_score >= Decimal("18")
        and _abs_change(candidate) >= Decimal("8")
        and confirmed
    ):
        reasons.append(
            "Extraordinary single-name tape (score ≥ 18, move ≥ 8%, confirmed)"
        )
        return "P0", reasons

    watch_boost = candidate.on_watchlist or candidate.in_opportunity_queue
    # Universe bar is intentionally high so only standout tape opens a queue row.
    # Watched/queued names get a slightly lower bar, still above noise.
    p1_bar = Decimal("58") if watch_boost else Decimal("68")
    market_wide = (
        (context is not None and context.status == "market_event")
        or candidate.evidence.get("move_scope") == "market"
    ) and not candidate.in_portfolio
    if (
        not market_wide
        and not _is_pulse_instrument(candidate)
        and not illiquid
        and confirmed
        and _has_strong_confirmation(candidate)
        and score >= p1_bar
        and (price_dim >= 50 or candidate.anomaly_score >= Decimal("12"))
    ):
        if watch_boost:
            reasons.append("Watched name with confirmed anomaly")
        else:
            reasons.append("Confirmed anomaly above the P1 bar")
        if (
            context
            and context.flagged_count >= 3
            and context.flagged_ratio >= Decimal("0.4")
        ):
            reasons.append(
                f"Industry breadth {context.flagged_count}/{context.member_count}"
            )
        return "P1", reasons

    if market_wide and confirmed and score >= Decimal("50"):
        reasons.append("Market-wide move — hold on Radar, do not auto-open the queue")
        return "P2", reasons

    if illiquid and confirmed and score >= Decimal("50"):
        reasons.append("Would be P1 but dollar volume looks too thin to auto-open")
        return "P2", reasons

    if _is_pulse_instrument(candidate):
        reasons.append("Sector/market pulse instrument — observation only")
        return "P2" if score >= Decimal("45") else "P3", reasons

    if score >= Decimal("45") or confirmed:
        reasons.append(
            "Flagged and useful on Radar, not urgent enough to open a queue row"
        )
        return "P2", reasons

    reasons.append("Weak or unconfirmed threshold flag; stored as background")
    return "P3", reasons


def _write_industry_evidence(
    candidate: RadarCandidate, context: IndustryContext | None
) -> None:
    if context is None:
        candidate.evidence["move_scope"] = "none"
        return
    candidate.evidence["industry_key"] = context.key
    candidate.evidence["industry_label"] = context.label
    candidate.evidence["industry_member_count"] = context.member_count
    candidate.evidence["industry_flagged_count"] = context.flagged_count
    candidate.evidence["industry_flagged_ratio"] = str(context.flagged_ratio)
    candidate.evidence["industry_status"] = context.status
    if context.median_change_pct is not None:
        candidate.evidence["industry_median_change_pct"] = str(context.median_change_pct)
    candidate.evidence["related_tickers"] = list(candidate.related_tickers)
    candidate.evidence["move_scope"] = _move_scope(candidate, context)


def _write_priority_evidence(candidate: RadarCandidate) -> None:
    candidate.care_tier = care_tier(candidate)
    candidate.evidence["radar_priority"] = candidate.radar_priority
    candidate.evidence["priority_score"] = str(candidate.priority_score)
    candidate.evidence["priority_reasons"] = list(candidate.priority_reasons)
    candidate.evidence["dimension_scores"] = dict(candidate.dimension_scores)
    candidate.evidence["care_tier"] = candidate.care_tier
    candidate.evidence["in_portfolio"] = candidate.in_portfolio
    candidate.evidence["in_opportunity_queue"] = candidate.in_opportunity_queue
    candidate.evidence["auto_promote"] = candidate.should_auto_promote


def _is_portfolio_risk(candidate: RadarCandidate) -> bool:
    if "risk_drop" in candidate.flags:
        return True
    if candidate.change_pct is not None and candidate.change_pct <= Decimal("-3"):
        return True
    z_score = _price_z(candidate)
    if z_score is not None and abs(z_score) >= Decimal("2"):
        return True
    return candidate.anomaly_score >= Decimal("10")


def _has_confirmation(candidate: RadarCandidate) -> bool:
    if {
        "volume_anomaly",
        "unusual_volume",
        "sector_relative_move",
        "price_anomaly",
    } & set(candidate.flags):
        return True
    z_score = _price_z(candidate)
    if z_score is not None and abs(z_score) >= Decimal("2"):
        return True
    volume_z = _decimal(candidate.evidence.get("volume_zscore"))
    return volume_z is not None and volume_z >= Decimal("2")


def _has_strong_confirmation(candidate: RadarCandidate) -> bool:
    """P1 auto-promote needs a price signal plus volume or sector residual."""
    z_score = _price_z(candidate)
    price_ok = (
        "price_anomaly" in candidate.flags
        or (z_score is not None and abs(z_score) >= Decimal("2.5"))
        or _abs_change(candidate) >= Decimal("4")
    )
    volume_z = _decimal(candidate.evidence.get("volume_zscore"))
    volume_ok = (
        "volume_anomaly" in candidate.flags
        or "unusual_volume" in candidate.flags
        or (
            candidate.volume_ratio is not None
            and candidate.volume_ratio >= Decimal("2")
        )
        or (volume_z is not None and volume_z >= Decimal("2"))
    )
    relative = _relative_pct(candidate)
    relative_ok = "sector_relative_move" in candidate.flags or (
        relative is not None and abs(relative) >= Decimal("3")
    )
    return price_ok and (volume_ok or relative_ok)


def _is_illiquid(candidate: RadarCandidate) -> bool:
    if (candidate.currency or "USD") != "USD":
        return False
    dollar = _decimal(candidate.evidence.get("avg_dollar_volume"))
    if dollar is None:
        return False
    return dollar < Decimal(RADAR_ILLIQUID_USD_DOLLAR_VOLUME)


def _is_pulse_instrument(candidate: RadarCandidate) -> bool:
    return candidate.ticker.upper() in RADAR_PULSE_TICKERS


def _price_dimension(candidate: RadarCandidate) -> int | None:
    z_score = _price_z(candidate)
    if z_score is not None:
        return _clip((float(abs(z_score)) / 4.0) * 100)
    change = _abs_change(candidate)
    if change == 0:
        return 0 if candidate.flags else None
    return _clip((float(change) / 12.0) * 100)


def _volume_dimension(candidate: RadarCandidate) -> int | None:
    volume_z = _decimal(candidate.evidence.get("volume_zscore"))
    if volume_z is not None:
        return _clip((float(max(volume_z, Decimal("0"))) / 4.0) * 100)
    if candidate.volume_ratio is not None:
        return _clip((float(candidate.volume_ratio) / 6.0) * 100)
    return None


def _relative_dimension(candidate: RadarCandidate) -> int | None:
    relative = _relative_pct(candidate)
    if relative is None:
        return None
    return _clip((float(abs(relative)) / 8.0) * 100)


def _industry_dimension(context: IndustryContext | None) -> int | None:
    if context is None or context.member_count < 3:
        return None
    return _clip(float(context.flagged_ratio) * 100)


def _watchlist_dimension(candidate: RadarCandidate) -> int:
    if candidate.on_watchlist:
        return 80
    if candidate.in_opportunity_queue:
        return 55
    return 0


def _weighted_score(dimensions: dict[str, int | None]) -> Decimal:
    used = {key: value for key, value in dimensions.items() if value is not None}
    weights = {key: _WEIGHTS[key] for key in used if key in _WEIGHTS}
    total = sum(weights.values())
    if not used or total <= 0:
        return Decimal("0.00")
    raw = sum(used[key] * (weights[key] / total) for key in used)
    return Decimal(str(raw)).quantize(Decimal("0.01"))


def _facts(candidate: RadarCandidate) -> dict[str, Any]:
    return {
        "price": _text(candidate.price),
        "currency": candidate.currency,
        "change_pct": _text(candidate.change_pct),
        "volume": candidate.volume,
        "avg_volume": candidate.avg_volume,
        "volume_ratio": _text(candidate.volume_ratio),
        "price_return_zscore": _text(_price_z(candidate)),
        "volume_zscore": candidate.evidence.get("volume_zscore"),
        "volatility_ratio": candidate.evidence.get("volatility_ratio"),
        "sector_relative_return_pct": candidate.evidence.get(
            "sector_relative_return_pct"
        ),
        "sector_benchmark": candidate.evidence.get("sector_benchmark"),
        "scan_state": candidate.evidence.get("scan_state"),
        "scan_delta_change_pct": candidate.evidence.get("scan_delta_change_pct"),
        "history_gap": candidate.evidence.get("history_gap"),
        "bar_count": candidate.evidence.get("bar_count"),
        "industry_status": candidate.evidence.get("industry_status"),
        "move_scope": candidate.evidence.get("move_scope"),
        "industry_median_change_pct": candidate.evidence.get(
            "industry_median_change_pct"
        ),
        "avg_dollar_volume": candidate.evidence.get("avg_dollar_volume"),
        "source": candidate.source,
        "source_as_of": (
            candidate.source_as_of.isoformat() if candidate.source_as_of else None
        ),
    }


def _promotion_rule(candidate: RadarCandidate) -> str:
    if candidate.radar_priority == "P0":
        return "Auto-promote: P0 position risk or extraordinary tape"
    if candidate.radar_priority == "P1":
        return "Auto-promote: P1 confirmed anomaly"
    if candidate.radar_priority == "P2":
        return "Hold on Radar: research candidate, no auto-promote"
    if candidate.radar_priority == "P3":
        return "Hold on Radar: background observation, no auto-promote"
    return "Not flagged"


def heat_for_status(status: str) -> str:
    if status in {"industry_event", "market_event"}:
        return "unusual"
    if status == "isolated_names":
        return "heating"
    return "quiet"


def industry_key(member: Any) -> str:
    return _industry_key(member)


def _industry_key(member: Any) -> str:
    label = (
        getattr(member, "industry", None)
        or getattr(member, "sector", None)
        or "unclassified"
    )
    jurisdiction = getattr(member, "jurisdiction", "") or "unknown"
    return f"{jurisdiction}:{str(label).strip().lower()}"


def _member_is_flagged(member: Any) -> bool:
    ticker = str(getattr(member, "ticker", "") or "").upper()
    if ticker in RADAR_PULSE_TICKERS:
        return False
    if isinstance(member, RadarCandidate):
        return is_flagged(member)
    return bool(getattr(member, "flags", None))


def _industry_status_without_market(
    flagged_count: int, member_count: int, ratio: Decimal
) -> str:
    if flagged_count <= 0:
        return "quiet"
    if (
        ratio >= INDUSTRY_EVENT_RATIO
        or (flagged_count >= INDUSTRY_EVENT_MIN_FLAGGED and member_count >= 4)
    ):
        return "industry_event"
    return "isolated_names"


def _is_industry_event(context: IndustryContext) -> bool:
    return context.status == "industry_event"


def _with_status(context: IndustryContext, status: str) -> IndustryContext:
    if context.status == status:
        return context
    return IndustryContext(
        key=context.key,
        label=context.label,
        jurisdiction=context.jurisdiction,
        member_count=context.member_count,
        flagged_count=context.flagged_count,
        flagged_ratio=context.flagged_ratio,
        median_change_pct=context.median_change_pct,
        median_volume_ratio=context.median_volume_ratio,
        declining_count=context.declining_count,
        advancing_count=context.advancing_count,
        related_tickers=context.related_tickers,
        status=status,
    )


def _market_event_jurisdictions(
    contexts: dict[str, IndustryContext], members: Sequence[Any]
) -> set[str]:
    by_jurisdiction: dict[str, list[IndustryContext]] = defaultdict(list)
    for context in contexts.values():
        if context.jurisdiction in {"", "mixed"}:
            continue
        by_jurisdiction[context.jurisdiction].append(context)

    flagged_by_jurisdiction: dict[str, list[Any]] = defaultdict(list)
    names_by_jurisdiction: dict[str, list[Any]] = defaultdict(list)
    for member in members:
        jurisdiction = str(getattr(member, "jurisdiction", "") or "")
        if not jurisdiction:
            continue
        names_by_jurisdiction[jurisdiction].append(member)
        if _member_is_flagged(member):
            flagged_by_jurisdiction[jurisdiction].append(member)

    market: set[str] = set()
    for jurisdiction, industries in by_jurisdiction.items():
        sizable = [item for item in industries if item.member_count >= 2]
        if not sizable:
            continue
        industry_events = [item for item in sizable if _is_industry_event(item)]
        industry_share = (
            Decimal(len(industry_events)) / Decimal(len(sizable))
        ).quantize(Decimal("0.01"))
        names = names_by_jurisdiction.get(jurisdiction, [])
        flagged = flagged_by_jurisdiction.get(jurisdiction, [])
        name_share = (
            (Decimal(len(flagged)) / Decimal(len(names))).quantize(Decimal("0.01"))
            if names
            else Decimal("0")
        )
        if (
            len(industry_events) >= MARKET_EVENT_MIN_INDUSTRY_EVENTS
            and industry_share >= MARKET_EVENT_INDUSTRY_SHARE
        ) or (
            len(flagged) >= MARKET_EVENT_MIN_FLAGGED
            and name_share >= MARKET_EVENT_NAME_RATIO
        ):
            market.add(jurisdiction)
    return market


def _move_scope(candidate: RadarCandidate, context: IndustryContext) -> str:
    if not is_flagged(candidate) or _is_pulse_instrument(candidate):
        return "none"
    if context.status == "market_event":
        return "market"
    if context.status == "industry_event":
        return "industry"
    return "isolated"


def _price_z(candidate: RadarCandidate) -> Decimal | None:
    return _decimal(candidate.evidence.get("price_return_zscore")) or _decimal(
        candidate.evidence.get("price_return_zscore")
    )


def _relative_pct(candidate: RadarCandidate) -> Decimal | None:
    return _decimal(candidate.evidence.get("sector_relative_return_pct"))


def _abs_change(candidate: RadarCandidate) -> Decimal:
    if candidate.change_pct is None:
        return Decimal("0")
    return abs(candidate.change_pct)


def _signed_pct(value: Decimal | None) -> str:
    if value is None:
        return "without a usable % move"
    sign = "+" if value > 0 else ""
    return f"{sign}{value}%"


def _median_decimal(values: list[float]) -> Decimal | None:
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return Decimal(str(values[mid])).quantize(Decimal("0.01"))
    return (
        (Decimal(str(values[mid - 1])) + Decimal(str(values[mid]))) / Decimal("2")
    ).quantize(Decimal("0.01"))


def _text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _clip(value: float) -> int:
    return max(0, min(100, int(round(value))))
