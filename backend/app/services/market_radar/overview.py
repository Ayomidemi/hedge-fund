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
from app.core.market_constants import RADAR_POST_CLOSE_WINDOW_HOURS
from app.models import RadarRun, RadarSnapshot
from app.services.market_data.sessions import ALL_JURISDICTIONS, session_for
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
    industries = _group_industries(working, watchlist_tickers)

    return MarketRadarOverviewResponse(
        generated_at=now,
        sessions=sessions,
        latest_run=_run_response(latest_run) if latest_run else None,
        working_set_count=len(working),
        flagged_count=len(flagged),
        industries=industries,
        working_set=[
            _name_response(row, watchlist_tickers) for row in _sorted(working)
        ],
        flagged=[_name_response(row, watchlist_tickers) for row in _sorted(flagged)],
        watchlist=watchlist_items,
        scan_changes=[
            _name_response(row, watchlist_tickers)
            for row in _sorted(_scan_changes(working))
        ],
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
    row: RadarSnapshot, watchlist_tickers: set[str] | None = None
) -> MarketRadarNameResponse:
    evidence = dict(row.evidence or {})
    watchlist = bool(
        (watchlist_tickers and row.ticker.upper() in watchlist_tickers)
        or evidence.get("on_watchlist")
    )
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
        flags=list(row.flags or []),
        evidence=evidence,
        sparkline=list(row.sparkline or []),
        as_of=row.as_of,
        source_as_of=row.source_as_of,
        carried_forward=row.carried_forward,
        stale_reason=row.stale_reason,
        on_watchlist=watchlist,
        pinned_prior=bool(evidence.get("pinned_prior")),
    )


def _group_industries(
    rows: list[RadarSnapshot], watchlist_tickers: set[str] | None = None
) -> list[MarketRadarIndustryResponse]:
    grouped: dict[str, list[RadarSnapshot]] = {}
    for row in rows:
        key = row.industry or row.sector or "Unclassified"
        grouped.setdefault(key, []).append(row)

    industries: list[MarketRadarIndustryResponse] = []
    for name, members in grouped.items():
        flagged = [row for row in members if row.flags]
        industries.append(
            MarketRadarIndustryResponse(
                name=name,
                jurisdiction=members[0].jurisdiction if len({m.jurisdiction for m in members}) == 1 else "mixed",
                name_count=len(members),
                flagged_count=len(flagged),
                heat=_heat(flagged, members),
                names=[
                    _name_response(row, watchlist_tickers)
                    for row in _sorted(members)
                ],
            )
        )
    industries.sort(key=lambda item: (item.flagged_count, item.name_count), reverse=True)
    return industries


def _heat(flagged: list[RadarSnapshot], members: list[RadarSnapshot]) -> str:
    if not members:
        return "quiet"
    ratio = len(flagged) / len(members)
    if ratio >= 0.4 or len(flagged) >= 3:
        return "unusual"
    if ratio > 0 or any(
        abs(float(row.change_pct or 0)) >= 2 for row in members
    ):
        return "heating"
    return "quiet"


def _sorted(rows: list[RadarSnapshot]) -> list[RadarSnapshot]:
    return sorted(rows, key=lambda row: row.anomaly_score, reverse=True)


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
