from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.market_radar import (
    MarketRadarIndustryResponse,
    MarketRadarNameResponse,
    MarketRadarOverviewResponse,
    MarketRadarRunResponse,
    MarketRadarSessionResponse,
)
from app.core.market_constants import (
    RADAR_POST_CLOSE_WINDOW_HOURS,
    RADAR_PULSE_TICKERS,
)
from app.models import RadarRun, RadarSnapshot
from app.services.market_data.sessions import ALL_JURISDICTIONS, session_for
from app.services.market_radar.priority import (
    IndustryContext,
    build_industry_contexts,
    heat_for_status,
    industry_key,
)
from app.services.market_radar.watchlist_book import list_watchlist


async def build_radar_overview(
    session: AsyncSession,
    *,
    jurisdiction: str | None = None,
    owner_user_id: str | None = None,
) -> MarketRadarOverviewResponse:
    now = datetime.now(timezone.utc)
    sessions = [
        _session_response(item, now)
        for item in ALL_JURISDICTIONS
        if jurisdiction in {None, "all", item}
    ]

    latest_run = await session.scalar(
        select(RadarRun)
        .where(RadarRun.status == "completed")
        .order_by(RadarRun.started_at.desc())
        .limit(1)
    )
    snapshot_run = await session.scalar(
        select(RadarRun)
        .options(selectinload(RadarRun.snapshots))
        .where(RadarRun.status == "completed")
        .where(RadarRun.working_set_count > 0)
        .order_by(RadarRun.started_at.desc())
        .limit(1)
    )

    snapshots = list(snapshot_run.snapshots) if snapshot_run else []
    if jurisdiction in ALL_JURISDICTIONS:
        snapshots = [row for row in snapshots if row.jurisdiction == jurisdiction]

    working = [row for row in snapshots if row.in_working_set]
    flagged = [row for row in working if row.flags]
    watchlist_tickers: set[str] = set()
    watchlist_items = []
    if owner_user_id:
        watchlist = await list_watchlist(session, owner_user_id=owner_user_id)
        watchlist_items = watchlist.items
        watchlist_tickers = {item.ticker.upper() for item in watchlist_items}
    contexts = build_industry_contexts(working)

    def named(row: RadarSnapshot) -> MarketRadarNameResponse:
        return _name_response(
            row,
            watchlist_tickers,
            context=contexts.get(industry_key(row)),
        )

    industries = _group_industries(working, watchlist_tickers, contexts)
    named_flagged = [named(row) for row in _sorted(flagged)]
    queue_candidates = [
        item
        for item in named_flagged
        if item.auto_promote or item.radar_priority in {"P0", "P1"}
    ]
    queue_tickers = {item.ticker for item in queue_candidates}
    desk_alerts = [
        item
        for item in named_flagged
        if item.care_tier in {"position", "watchlist", "queue"}
        and item.ticker not in queue_tickers
    ]
    desk_alerts.sort(
        key=lambda item: (
            {"position": 0, "watchlist": 1, "queue": 2}.get(item.care_tier, 9),
            item.ticker,
        )
    )

    return MarketRadarOverviewResponse(
        generated_at=now,
        sessions=sessions,
        latest_run=_run_response(latest_run) if latest_run else None,
        working_set_count=len(working),
        flagged_count=len(flagged),
        p0_count=_priority_count(flagged, "P0"),
        p1_count=_priority_count(flagged, "P1"),
        p2_count=_priority_count(flagged, "P2"),
        p3_count=_priority_count(flagged, "P3"),
        industries=industries,
        working_set=[named(row) for row in _sorted(working)],
        flagged=named_flagged,
        queue_candidates=queue_candidates,
        desk_alerts=desk_alerts,
        watchlist=watchlist_items,
        scan_changes=[named(row) for row in _sorted(_scan_changes(working))],
    )


def _session_response(jurisdiction: str, now: datetime) -> MarketRadarSessionResponse:
    state = session_for(
        jurisdiction, now, post_close_hours=RADAR_POST_CLOSE_WINDOW_HOURS
    )
    return MarketRadarSessionResponse(
        jurisdiction=jurisdiction,
        is_open=state.is_open,
        in_post_close_window=state.in_post_close_window,
        allows_discovery=state.allows_discovery,
        label=state.label,
        vendors=["ngnmarket"] if jurisdiction == "NG" else ["fmp", "tiingo", "polygon"],
    )


def _run_response(run: RadarRun) -> MarketRadarRunResponse:
    return MarketRadarRunResponse(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        triggered_by_user_id=run.triggered_by_user_id,
        jurisdictions_requested=list(run.jurisdictions_requested or []),
        jurisdictions_scanned=list(run.jurisdictions_scanned or []),
        jurisdictions_skipped=list(run.jurisdictions_skipped or []),
        vendor_calls=run.vendor_calls,
        cache_hits=run.cache_hits,
        catalog_count=run.catalog_count,
        working_set_count=run.working_set_count,
        flagged_count=run.flagged_count,
        promoted_count=run.promoted_count,
        promotion_owner_ids=list(run.promotion_owner_ids or []),
        notes=list(run.notes or []),
        errors=list(run.errors or []),
    )


def _name_response(
    row: RadarSnapshot,
    watchlist_tickers: set[str] | None = None,
    context: IndustryContext | None = None,
) -> MarketRadarNameResponse:
    evidence = dict(row.evidence or {})
    watchlist = bool(
        (watchlist_tickers and row.ticker.upper() in watchlist_tickers)
        or evidence.get("on_watchlist")
    )
    if context is not None:
        evidence["industry_status"] = context.status
        evidence["move_scope"] = _live_move_scope(row, context)
    return MarketRadarNameResponse(
        ticker=row.ticker,
        name=row.name,
        jurisdiction=row.jurisdiction,
        sector=row.sector,
        industry=row.industry,
        asset_class=row.asset_class,
        currency=row.currency,
        source=row.source,
        always_watched=row.always_watched,
        price=row.price,
        change_pct=row.change_pct,
        volume=row.volume,
        volume_ratio=row.volume_ratio,
        anomaly_score=row.anomaly_score,
        radar_priority=_priority_value(row, evidence),
        priority_score=row.priority_score
        if getattr(row, "priority_score", None) is not None
        else _decimal_or_none(evidence.get("priority_score")),
        auto_promote=bool(
            getattr(row, "auto_promote", False) or evidence.get("auto_promote")
        ),
        priority_reasons=list(evidence.get("priority_reasons") or []),
        flags=list(row.flags or []),
        evidence=evidence,
        sparkline=list(row.sparkline or []),
        as_of=row.as_of,
        source_as_of=row.source_as_of,
        carried_forward=row.carried_forward,
        stale_reason=row.stale_reason,
        on_watchlist=watchlist,
        pinned_prior=bool(evidence.get("pinned_prior")),
        in_portfolio=bool(evidence.get("in_portfolio")),
        care_tier=_care_tier_value(row, evidence, watchlist),
    )


def _live_move_scope(row: RadarSnapshot, context: IndustryContext) -> str:
    ticker = (row.ticker or "").upper()
    if ticker in RADAR_PULSE_TICKERS or not row.flags:
        return "none"
    if context.status == "market_event":
        return "market"
    if context.status == "industry_event":
        return "industry"
    return "isolated"


def _group_industries(
    rows: list[RadarSnapshot],
    watchlist_tickers: set[str] | None,
    contexts: dict[str, IndustryContext],
) -> list[MarketRadarIndustryResponse]:
    grouped: dict[str, list[RadarSnapshot]] = {}
    for row in rows:
        grouped.setdefault(industry_key(row), []).append(row)

    industries: list[MarketRadarIndustryResponse] = []
    for key, members in grouped.items():
        context = contexts.get(key)
        status = context.status if context is not None else "quiet"
        industries.append(
            MarketRadarIndustryResponse(
                name=(
                    context.label
                    if context is not None
                    else (members[0].industry or members[0].sector or "Unclassified")
                ),
                jurisdiction=(
                    context.jurisdiction
                    if context is not None
                    else members[0].jurisdiction
                ),
                name_count=len(members),
                flagged_count=(
                    context.flagged_count
                    if context is not None
                    else len([row for row in members if row.flags])
                ),
                heat=heat_for_status(status),
                status=status,
                median_change_pct=(
                    context.median_change_pct if context is not None else None
                ),
                median_volume_ratio=(
                    context.median_volume_ratio if context is not None else None
                ),
                declining_count=context.declining_count if context is not None else 0,
                advancing_count=context.advancing_count if context is not None else 0,
                names=[
                    _name_response(row, watchlist_tickers, context)
                    for row in _sorted(members)
                ],
            )
        )
    industries.sort(key=lambda item: (item.flagged_count, item.name_count), reverse=True)
    return industries


_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _sorted(rows: list[RadarSnapshot]) -> list[RadarSnapshot]:
    return sorted(
        rows,
        key=lambda row: (
            _PRIORITY_RANK.get(_priority_value(row, row.evidence or {}), 9),
            -(row.anomaly_score or 0),
        ),
    )


def _priority_value(row: RadarSnapshot, evidence: dict) -> str | None:
    return getattr(row, "radar_priority", None) or evidence.get("radar_priority")


def _care_tier_value(
    _row: RadarSnapshot, evidence: dict, watchlist: bool
) -> str:
    stored = evidence.get("care_tier")
    if stored in {"position", "watchlist", "queue", "universe"}:
        return stored
    if evidence.get("in_portfolio"):
        return "position"
    if watchlist:
        return "watchlist"
    if evidence.get("in_opportunity_queue"):
        return "queue"
    return "universe"


def _priority_count(rows: list[RadarSnapshot], priority: str) -> int:
    return sum(
        1
        for row in rows
        if _priority_value(row, row.evidence or {}) == priority
    )


def _decimal_or_none(value: object):
    from decimal import Decimal, InvalidOperation

    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _scan_changes(rows: list[RadarSnapshot]) -> list[RadarSnapshot]:
    changed: list[RadarSnapshot] = []
    for row in rows:
        flags = set(row.flags or [])
        evidence = row.evidence or {}
        state = str(evidence.get("scan_state") or "")
        if "scan_lurch" in flags or state in {
            "accelerating",
            "rebounding",
            "selling_off",
            "cooling",
        }:
            changed.append(row)
    return changed
