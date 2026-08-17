"""Run a jurisdiction-aware market radar scan.

Vendor calls are gated by session state. A closed US market never hits
FMP/Tiingo/Polygon. A closed NGX never hits NGN Market.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.market_constants import (
    PRICE_BATCH_SIZE,
    RADAR_POST_CLOSE_WINDOW_HOURS,
    RADAR_WORKING_SET_SIZE,
)
from app.models import Instrument, Opportunity, Portfolio, RadarRun, RadarSnapshot
from app.api.schemas.operating_core import InstrumentCreate
from app.services.administration.system_log import record_system_log
from app.services.market_data.quote_provider import fetch_quotes
from app.services.market_data.sessions import (
    ALL_JURISDICTIONS,
    JURISDICTION_NG,
    JURISDICTION_US,
    session_for,
)
from app.services.market_radar.providers import fetch_ngn_discovery, fetch_us_movers
from app.services.market_radar.scoring import RadarCandidate, is_flagged, score_candidate
from app.services.market_radar.watchlist import load_always_watched
from app.services.portfolio.operating_core import upsert_instrument

logger = logging.getLogger(__name__)


async def run_radar_scan(
    session: AsyncSession,
    *,
    jurisdictions: list[str] | None = None,
    force: bool = False,
    owner_user_id: str | None = None,
) -> RadarRun:
    started_at = datetime.now(timezone.utc)
    requested = [
        item
        for item in (jurisdictions or list(ALL_JURISDICTIONS))
        if item in ALL_JURISDICTIONS
    ] or list(ALL_JURISDICTIONS)

    run = RadarRun(
        started_at=started_at,
        status="running",
        jurisdictions_requested=requested,
    )
    session.add(run)
    await session.flush()

    scanned: list[str] = []
    skipped: list[dict] = []
    notes: list[str] = []
    errors: list[dict] = []
    vendor_calls = 0
    candidates: dict[str, RadarCandidate] = {}
    working: list[RadarCandidate] = []
    flagged: list[RadarCandidate] = []
    promoted = 0

    try:
        watched = await load_always_watched(session)

        for jurisdiction in requested:
            state = session_for(
                jurisdiction,
                started_at,
                post_close_hours=RADAR_POST_CLOSE_WINDOW_HOURS,
            )
            if not force and not state.allows_discovery:
                skipped.append(
                    {
                        "jurisdiction": jurisdiction,
                        "reason": state.label,
                        "vendors_not_called": _vendors_for(jurisdiction),
                    }
                )
                notes.append(
                    f"{jurisdiction} skipped ({state.label}); "
                    f"no calls to {', '.join(_vendors_for(jurisdiction))}."
                )
                continue

            scanned.append(jurisdiction)
            for ticker, candidate in watched.candidates.items():
                if candidate.jurisdiction == jurisdiction:
                    candidates[ticker] = candidate

            if jurisdiction == JURISDICTION_US:
                movers, calls, vendor_errors = await fetch_us_movers()
                vendor_calls += calls
                _merge(candidates, movers)
                errors.extend({"error": message} for message in vendor_errors)
                if not state.allows_live_quotes and not force:
                    notes.append(
                        "US post-close: using discovery lists only, no extra quote batch."
                    )
                else:
                    missing = [
                        ticker
                        for ticker, item in candidates.items()
                        if item.jurisdiction == JURISDICTION_US
                        and item.always_watched
                        and item.price is None
                    ]
                    if missing:
                        vendor_calls += max(
                            1,
                            (len(missing) + PRICE_BATCH_SIZE - 1) // PRICE_BATCH_SIZE,
                        )
                        quotes = await fetch_quotes(missing)
                        _apply_quotes(candidates, quotes)
            elif jurisdiction == JURISDICTION_NG:
                discovered, calls, vendor_errors = await fetch_ngn_discovery()
                vendor_calls += calls
                _merge(candidates, discovered)
                errors.extend({"error": message} for message in vendor_errors)
                missing = [
                    ticker
                    for ticker, item in candidates.items()
                    if item.jurisdiction == JURISDICTION_NG
                    and item.always_watched
                    and item.price is None
                ]
                if missing and (state.allows_live_quotes or force):
                    notes.append(
                        f"NGX quoting {len(missing)} always-watched name(s); "
                        "discovery lists are not per-symbol searched."
                    )
                    vendor_calls += len(missing)
                    quotes = await fetch_quotes(missing)
                    _apply_quotes(candidates, quotes)

        if scanned:
            await _carry_forward_skipped(
                session,
                candidates,
                skipped_jurisdictions={item["jurisdiction"] for item in skipped},
            )
            for candidate in candidates.values():
                score_candidate(candidate)
            working = _select_working_set(list(candidates.values()))
            working_tickers = {item.ticker for item in working}
            for candidate in candidates.values():
                session.add(
                    _snapshot_from_candidate(run.id, candidate, working_tickers, started_at)
                )
            flagged = [item for item in working if is_flagged(item)]
            if flagged:
                promoted = await promote_flagged_candidates(
                    session, flagged, owner_user_id=owner_user_id
                )
        else:
            notes.append("No open sessions; last working set left unchanged.")

        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.jurisdictions_scanned = scanned
        run.jurisdictions_skipped = skipped
        run.vendor_calls = vendor_calls
        run.working_set_count = len(working)
        run.flagged_count = len(flagged)
        run.promoted_count = promoted
        run.errors = errors
        run.notes = notes

        await record_system_log(
            session,
            owner_user_id=owner_user_id,
            category="market_data",
            event="radar_scan_completed",
            level="warning" if errors else "info",
            message=(
                f"Radar scanned {', '.join(scanned) or 'no markets'}: "
                f"{len(working)} working-set names, {len(flagged)} flagged, "
                f"{vendor_calls} vendor calls."
            ),
            context={
                "run_id": str(run.id),
                "scanned": scanned,
                "skipped": skipped,
                "vendor_calls": vendor_calls,
            },
        )
        await session.commit()
    except Exception as exc:
        logger.exception("radar_scan_failed")
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        run.jurisdictions_scanned = scanned
        run.jurisdictions_skipped = skipped
        run.vendor_calls = vendor_calls
        run.errors = errors + [{"error": str(exc)}]
        run.notes = notes
        await session.commit()
        return run

    logger.info(
        "radar_scan_completed",
        extra={
            "run_id": str(run.id),
            "scanned": scanned,
            "skipped": skipped,
            "vendor_calls": vendor_calls,
            "working_set": len(working),
        },
    )
    return run


def _vendors_for(jurisdiction: str) -> list[str]:
    if jurisdiction == JURISDICTION_NG:
        return ["ngnmarket"]
    return ["fmp", "tiingo", "polygon"]


def _merge(target: dict[str, RadarCandidate], incoming: list[RadarCandidate]) -> None:
    for item in incoming:
        existing = target.get(item.ticker)
        if existing is None:
            target[item.ticker] = item
            continue
        if item.price is not None:
            existing.price = item.price
        if item.change_pct is not None:
            existing.change_pct = item.change_pct
        if item.volume is not None:
            existing.volume = item.volume
        if item.avg_volume is not None:
            existing.avg_volume = item.avg_volume
        if item.sector and not existing.sector:
            existing.sector = item.sector
        if item.source and existing.source in {"seed", "book", ""}:
            existing.source = item.source
        for flag in item.flags:
            if flag not in existing.flags:
                existing.flags.append(flag)


def _apply_quotes(candidates: dict[str, RadarCandidate], quotes) -> None:
    for ticker, quote in quotes.items():
        item = candidates.get(ticker)
        if item is None:
            continue
        item.price = quote.price
        item.previous_close = quote.previous_close or item.previous_close
        item.change_pct = quote.change_pct if quote.change_pct is not None else item.change_pct
        item.volume = quote.volume if quote.volume is not None else item.volume
        item.source = quote.source
        if quote.currency:
            item.currency = quote.currency


def _select_working_set(candidates: list[RadarCandidate]) -> list[RadarCandidate]:
    always = [item for item in candidates if item.always_watched]
    rest = [item for item in candidates if not item.always_watched]
    rest.sort(key=lambda item: item.anomaly_score, reverse=True)
    remaining = max(RADAR_WORKING_SET_SIZE - len(always), 0)
    return always + rest[:remaining]


async def _carry_forward_skipped(
    session: AsyncSession,
    candidates: dict[str, RadarCandidate],
    *,
    skipped_jurisdictions: set[str],
) -> None:
    """Keep the last open-session names on screen when a market is closed."""
    if not skipped_jurisdictions:
        return
    previous = await session.scalar(
        select(RadarRun)
        .options(selectinload(RadarRun.snapshots))
        .where(RadarRun.status == "completed")
        .where(RadarRun.working_set_count > 0)
        .order_by(RadarRun.started_at.desc())
        .limit(1)
    )
    if previous is None:
        return
    for snapshot in previous.snapshots:
        if snapshot.jurisdiction not in skipped_jurisdictions:
            continue
        if snapshot.ticker in candidates:
            continue
        candidates[snapshot.ticker] = RadarCandidate(
            ticker=snapshot.ticker,
            name=snapshot.name,
            jurisdiction=snapshot.jurisdiction,
            sector=snapshot.sector,
            industry=snapshot.industry,
            asset_class=snapshot.asset_class,
            exchange=snapshot.exchange,
            currency=snapshot.currency,
            source=snapshot.source,
            always_watched=snapshot.always_watched,
            price=snapshot.price,
            previous_close=snapshot.previous_close,
            change_pct=snapshot.change_pct,
            volume=snapshot.volume,
            avg_volume=snapshot.avg_volume,
            volume_ratio=snapshot.volume_ratio,
            anomaly_score=snapshot.anomaly_score,
            flags=list(snapshot.flags or []),
        )


def _snapshot_from_candidate(
    run_id,
    candidate: RadarCandidate,
    working_tickers: set[str],
    as_of: datetime,
) -> RadarSnapshot:
    return RadarSnapshot(
        run_id=run_id,
        ticker=candidate.ticker,
        name=candidate.name,
        jurisdiction=candidate.jurisdiction,
        sector=candidate.sector,
        industry=candidate.industry,
        asset_class=candidate.asset_class,
        exchange=candidate.exchange,
        currency=candidate.currency,
        source=candidate.source or "radar",
        always_watched=candidate.always_watched,
        in_working_set=candidate.ticker in working_tickers,
        price=candidate.price,
        previous_close=candidate.previous_close,
        change_pct=candidate.change_pct,
        volume=candidate.volume,
        avg_volume=candidate.avg_volume,
        volume_ratio=candidate.volume_ratio,
        anomaly_score=candidate.anomaly_score,
        flags=candidate.flags,
        as_of=as_of,
    )


async def promote_flagged_candidates(
    session: AsyncSession,
    flagged: list[RadarCandidate],
    *,
    owner_user_id: str | None,
    limit: int = 10,
) -> int:
    owner_ids = [owner_user_id] if owner_user_id else await _portfolio_owner_ids(session)
    if not owner_ids:
        return 0

    ranked = sorted(flagged, key=lambda item: item.anomaly_score, reverse=True)[:limit]
    promoted = 0
    now = datetime.now(timezone.utc)

    for owner in owner_ids:
        open_tickers = {
            ticker.upper()
            for ticker in await session.scalars(
                select(Instrument.ticker)
                .join(Opportunity, Opportunity.instrument_id == Instrument.id)
                .where(Opportunity.owner_user_id == owner)
                .where(Opportunity.closed_at.is_(None))
            )
        }
        for candidate in ranked:
            variants = {
                candidate.ticker,
                candidate.ticker.removesuffix(".NG"),
                f"{candidate.ticker.removesuffix('.NG')}.NG",
            }
            if open_tickers & variants:
                continue
            instrument = await session.scalar(
                select(Instrument).where(Instrument.ticker == candidate.ticker)
            )
            if instrument is None:
                instrument = await upsert_instrument(
                    session,
                    InstrumentCreate(
                        ticker=candidate.ticker,
                        name=candidate.name[:255],
                        asset_class=_asset_class(candidate.asset_class),
                        exchange=candidate.exchange,
                        currency=candidate.currency,
                        sector=candidate.sector,
                        industry=candidate.industry,
                    ),
                )
            flags = ", ".join(candidate.flags) or "unusual activity"
            move = (
                f" {candidate.change_pct}%."
                if candidate.change_pct is not None
                else "."
            )
            session.add(
                Opportunity(
                    owner_user_id=owner,
                    instrument_id=instrument.id,
                    discovered_at=now,
                    status="discovered",
                    priority="high"
                    if candidate.anomaly_score >= Decimal("12")
                    else "medium",
                    thesis=f"Radar flagged {candidate.ticker} ({flags}).{move}",
                    research_question=f"Does {candidate.ticker} deserve a Ticker Analyst review?",
                    next_action="Review on Ticker Analyst before any capital.",
                    notes=f"radar_score={candidate.anomaly_score} source={candidate.source}",
                    status_history=[
                        {
                            "status": "discovered",
                            "at": now.isoformat(),
                            "note": "Created by market radar.",
                        }
                    ],
                )
            )
            open_tickers.add(candidate.ticker)
            promoted += 1
    return promoted


def _asset_class(value: str | None) -> str:
    if value in {"equity", "etf", "bond", "commodity", "cash_equivalent", "other"}:
        return value
    return "equity"


async def _portfolio_owner_ids(session: AsyncSession) -> list[str]:
    return list(await session.scalars(select(Portfolio.owner_user_id).distinct()))
