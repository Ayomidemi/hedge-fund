"""Read-only replay of a stored radar scan. Run: python -m audits.radar_integrity.

Uses stored snapshot observations and the current historical store, bounded to
completed dates preceding that scan. This is a diagnostic, not a point-in-time
strategy backtest. No provider calls, scans, orders, or database writes.
"""
import asyncio
import json
import logging
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select, text
from app.db.session import AsyncSessionLocal, engine
from app.core.market_constants import RADAR_PULSE_TICKERS
from app.models import RadarRun, RadarSnapshot
from app.services.market_radar.scoring import RadarCandidate, score_candidate
from app.services.market_radar.priority import assign_priorities
from app.services.market_radar.scan import (
    _assess_observations, _apply_historical_evidence, _apply_sector_relative,
    _select_working_set, _coverage_note,
)


async def audit():
    async with AsyncSessionLocal() as session:
        await session.execute(text('SET TRANSACTION READ ONLY'))
        run = await session.scalar(select(RadarRun).where(
            RadarRun.status == 'completed', RadarRun.working_set_count > 0
        ).order_by(RadarRun.started_at.desc(), RadarRun.created_at.desc()).limit(1))
        if run is None:
            return {'error': 'No completed scan with observations.'}
        snapshots = list(await session.scalars(select(RadarSnapshot).where(RadarSnapshot.run_id == run.id)))
        candidates = []
        retained = {'quote_as_of', 'quote_source', 'discovery_lists', 'liquidity_rank'}
        for row in snapshots:
            evidence = row.evidence or {}
            candidates.append(RadarCandidate(
                ticker=row.ticker, name=row.name, jurisdiction=row.jurisdiction,
                sector=row.sector, industry=row.industry, asset_class=row.asset_class,
                currency=row.currency, source=row.source, source_as_of=row.source_as_of,
                price=row.price, previous_close=row.previous_close, change_pct=row.change_pct,
                volume=row.volume, always_watched=(row.ticker in RADAR_PULSE_TICKERS or any(
                    evidence.get(key) for key in ('in_portfolio', 'on_watchlist', 'in_opportunity_queue'))),
                carried_forward=row.carried_forward, stale_reason=row.stale_reason,
                on_watchlist=bool(evidence.get('on_watchlist')),
                pinned_prior=bool(evidence.get('pinned_prior')),
                in_portfolio=bool(evidence.get('in_portfolio')),
                in_opportunity_queue=bool(evidence.get('in_opportunity_queue')),
                evidence={key:value for key,value in evidence.items() if key in retained},
            ))
        at = run.finished_at or run.started_at
        _assess_observations(candidates, at)
        await _apply_historical_evidence(session, candidates, now=at)
        _apply_sector_relative(candidates)
        for candidate in candidates:
            score_candidate(candidate)
        assign_priorities(candidates)
        report = {
            'checked_at':datetime.now(timezone.utc).isoformat(),
            'scan_started_at':run.started_at.isoformat(), 'scan_finished_at':str(run.finished_at),
            'catalog_count':run.catalog_count, 'snapshot_count':len(snapshots),
            'stored_priorities':dict(Counter(row.radar_priority or 'unranked' for row in snapshots)),
            'replayed_priorities':dict(Counter(row.radar_priority or 'unranked' for row in candidates)),
            'observation_quality':dict(Counter(row.evidence.get('observation_quality') for row in candidates)),
            'history_gaps':dict(Counter(row.evidence.get('history_gap', 'none') for row in candidates)),
            'stored_working_set':run.working_set_count,
            'stored_protected_count':sum(row.always_watched for row in snapshots),
            'protected_count_from_recorded_current_membership':sum(row.always_watched for row in candidates),
            'replayed_working_set':len(_select_working_set(candidates)),
            'coverage':_coverage_note(candidates),
            'limitation':'Stored observations with currently available completed history; no replayed orders or profitability claim.',
        }
        await session.rollback()
        return report


async def main():
    try:
        print(json.dumps(await asyncio.wait_for(audit(), timeout=60), indent=2))
    finally:
        await engine.dispose()


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    asyncio.run(main())
