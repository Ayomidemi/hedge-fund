"""Run a jurisdiction-aware market radar scan.

Vendor calls are gated by session state. A closed US market never hits
FMP/Tiingo/Polygon. A closed NGX never hits NGN Market.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from math import sqrt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.market_constants import (
    PRICE_BATCH_SIZE,
    RADAR_HISTORY_LOOKBACK_DAYS,
    RADAR_NG_QUOTE_REFRESH_LIMIT,
    RADAR_POST_CLOSE_WINDOW_HOURS,
    RADAR_QUOTE_CACHE_TTL_SECONDS,
    RADAR_SECTOR_BENCHMARKS,
    RADAR_SPARKLINE_POINTS,
    RADAR_US_QUOTE_REFRESH_LIMIT,
    RADAR_VENDOR_QUOTE_SOURCES,
    RADAR_WORKING_SET_SIZE,
)
from app.models import (
    Instrument,
    InstrumentQuote,
    MarketPriceBar,
    Opportunity,
    Portfolio,
    RadarRun,
    RadarSnapshot,
)
from app.api.schemas.operating_core import InstrumentCreate
from app.services.administration.system_log import record_system_log
from app.services.market_data.ingestion import persist_quotes
from app.services.market_data.quote_provider import LiveQuote, fetch_quotes
from app.services.market_data.sessions import (
    ALL_JURISDICTIONS,
    JURISDICTION_NG,
    JURISDICTION_US,
    session_for,
)
from app.services.market_data.universe import quote_symbol_for
from app.services.market_radar.catalog import (
    load_catalog_candidates,
    sync_monitored_universe,
)
from app.services.market_radar.providers import fetch_ngn_discovery, fetch_us_movers
from app.services.market_radar.scoring import (
    RadarCandidate,
    is_flagged,
    score_candidate,
)
from app.services.market_radar.watchlist import load_always_watched
from app.services.portfolio.operating_core import upsert_instrument

logger = logging.getLogger(__name__)


async def run_radar_scan(
    session: AsyncSession,
    *,
    jurisdictions: list[str] | None = None,
    force: bool = False,
    triggered_by_user_id: str | None = None,
    owner_user_id: str | None = None,
) -> RadarRun:
    if triggered_by_user_id is None:
        triggered_by_user_id = owner_user_id
    started_at = datetime.now(timezone.utc)
    requested = [
        item
        for item in (jurisdictions or list(ALL_JURISDICTIONS))
        if item in ALL_JURISDICTIONS
    ] or list(ALL_JURISDICTIONS)

    run = RadarRun(
        started_at=started_at,
        status="running",
        triggered_by_user_id=triggered_by_user_id,
        jurisdictions_requested=requested,
    )
    session.add(run)
    await session.flush()

    scanned: list[str] = []
    skipped: list[dict] = []
    notes: list[str] = []
    errors: list[dict] = []
    vendor_calls = 0
    cache_hits = 0
    catalog_count = 0
    candidates: dict[str, RadarCandidate] = {}
    working: list[RadarCandidate] = []
    flagged: list[RadarCandidate] = []
    promotion_owner_ids: list[str] = []
    promoted = 0

    try:
        watched = await load_always_watched(session)
        catalog_sync = await sync_monitored_universe(session, watched=watched)
        catalog_count = catalog_sync.active_count

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
            _merge(
                candidates,
                await load_catalog_candidates(session, jurisdictions=[jurisdiction]),
            )
            for ticker, candidate in watched.candidates.items():
                if candidate.jurisdiction == jurisdiction:
                    _merge(candidates, [candidate])

            jurisdiction_candidates = [
                item for item in candidates.values() if item.jurisdiction == jurisdiction
            ]
            cache_hits += await _apply_cached_quotes(
                session,
                jurisdiction_candidates,
                now=started_at,
            )

            if jurisdiction == JURISDICTION_US:
                movers, calls, vendor_errors = await fetch_us_movers()
                vendor_calls += calls
                _merge(candidates, movers)
                errors.extend({"error": message} for message in vendor_errors)
                if not state.allows_live_quotes and not force:
                    notes.append(
                        "US post-close: using discovery lists only, no extra quote batch."
                    )
            elif jurisdiction == JURISDICTION_NG:
                discovered, calls, vendor_errors = await fetch_ngn_discovery()
                vendor_calls += calls
                _merge(candidates, discovered)
                errors.extend({"error": message} for message in vendor_errors)

            jurisdiction_candidates = [
                item for item in candidates.values() if item.jurisdiction == jurisdiction
            ]
            missing = _quote_targets(jurisdiction_candidates, jurisdiction)
            live_quotes: dict[str, LiveQuote] = {}
            if missing and (state.allows_live_quotes or force):
                if jurisdiction == JURISDICTION_NG:
                    notes.append(
                        f"NGX quoting {len(missing)} catalog/watchlist name(s); "
                        "per-symbol calls are capped."
                    )
                vendor_calls += _estimate_quote_calls(missing)
                live_quotes = await fetch_quotes(missing)
                _apply_quotes(candidates, live_quotes)

            persisted = await _persist_vendor_tapes(
                session,
                [item for item in candidates.values() if item.jurisdiction == jurisdiction],
                live_quotes,
                now=started_at,
            )
            if persisted:
                notes.append(f"{jurisdiction} stored {persisted} quote(s) for the next scan.")

        if scanned:
            await _carry_forward_skipped(
                session,
                candidates,
                skipped_jurisdictions={item["jurisdiction"] for item in skipped},
            )
            await _apply_historical_evidence(
                session,
                [item for item in candidates.values() if not item.carried_forward],
                now=started_at,
            )
            _apply_sector_relative(
                [item for item in candidates.values() if not item.carried_forward]
            )
            for candidate in candidates.values():
                if candidate.carried_forward:
                    continue
                score_candidate(candidate)
            working = _select_working_set(list(candidates.values()))
            working_tickers = {item.ticker for item in working}
            for candidate in candidates.values():
                session.add(
                    _snapshot_from_candidate(
                        run.id, candidate, working_tickers, started_at
                    )
                )
            flagged = [item for item in working if is_flagged(item)]
            promotable = [item for item in flagged if not item.carried_forward]
            if promotable:
                if triggered_by_user_id:
                    promotion_owner_ids = [triggered_by_user_id]
                else:
                    promotion_owner_ids = await _portfolio_owner_ids(session)
                promoted = await promote_flagged_candidates(
                    session,
                    promotable,
                    owner_ids=promotion_owner_ids,
                )
        else:
            notes.append("No open sessions; last working set left unchanged.")

        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.jurisdictions_scanned = scanned
        run.jurisdictions_skipped = skipped
        run.vendor_calls = vendor_calls
        run.cache_hits = cache_hits
        run.catalog_count = catalog_count
        run.working_set_count = len(working)
        run.flagged_count = len(flagged)
        run.promoted_count = promoted
        run.promotion_owner_ids = promotion_owner_ids
        run.errors = errors
        run.notes = notes

        await record_system_log(
            session,
            owner_user_id=triggered_by_user_id,
            category="market_data",
            event="radar_scan_completed",
            level="warning" if errors else "info",
            message=(
                f"Radar scanned {', '.join(scanned) or 'no markets'}: "
                f"{len(working)} working-set names, {len(flagged)} flagged, "
                f"{vendor_calls} vendor calls, {cache_hits} cache hits."
            ),
            context={
                "run_id": str(run.id),
                "scanned": scanned,
                "skipped": skipped,
                "vendor_calls": vendor_calls,
                "cache_hits": cache_hits,
                "catalog_count": catalog_count,
                "promotion_owner_ids": promotion_owner_ids,
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
        run.cache_hits = cache_hits
        run.catalog_count = catalog_count
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


def _merge(target: dict[str, RadarCandidate], incoming: Iterable[RadarCandidate]) -> None:
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
        if item.source_as_of and (
            existing.source_as_of is None or item.source_as_of > existing.source_as_of
        ):
            existing.source_as_of = item.source_as_of
        existing.always_watched = existing.always_watched or item.always_watched
        existing.is_catalog_member = existing.is_catalog_member or item.is_catalog_member
        existing.evidence.update(item.evidence)
        if item.sparkline:
            existing.sparkline = item.sparkline
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
        item.source_as_of = quote.as_of
        item.stale_reason = None
        item.evidence["quote_source"] = quote.source
        item.evidence["quote_as_of"] = quote.as_of.isoformat()
        if quote.currency:
            item.currency = quote.currency


async def _apply_cached_quotes(
    session: AsyncSession,
    candidates: list[RadarCandidate],
    *,
    now: datetime,
) -> int:
    instruments = await _load_instruments_by_quote_symbol(
        session, {candidate.ticker for candidate in candidates}
    )
    if not instruments:
        return 0
    quotes = {
        quote.instrument_id: quote
        for quote in await session.scalars(
            select(InstrumentQuote).where(
                InstrumentQuote.instrument_id.in_(
                    [instrument.id for instrument in instruments.values()]
                )
            )
        )
    }

    hits = 0
    for candidate in candidates:
        instrument = instruments.get(candidate.ticker)
        if instrument is None:
            continue
        quote = quotes.get(instrument.id)
        if quote is None:
            continue
        if not _quote_usable_for_radar(quote, now):
            if candidate.price is None:
                candidate.stale_reason = "stale quote"
            continue
        if candidate.price is not None and candidate.source in RADAR_VENDOR_QUOTE_SOURCES:
            continue
        if candidate.price is not None and candidate.source_as_of is not None:
            quote_as_of = _aware_utc(quote.as_of)
            candidate_as_of = _aware_utc(candidate.source_as_of)
            if quote_as_of < candidate_as_of:
                continue
        candidate.price = quote.price
        candidate.previous_close = quote.previous_close or candidate.previous_close
        candidate.change_pct = (
            quote.change_pct if quote.change_pct is not None else candidate.change_pct
        )
        candidate.volume = quote.volume if quote.volume is not None else candidate.volume
        candidate.currency = quote.currency or candidate.currency
        candidate.source = f"cache:{quote.source}"
        candidate.source_as_of = quote.as_of
        candidate.stale_reason = None
        candidate.evidence["quote_source"] = quote.source
        candidate.evidence["quote_as_of"] = quote.as_of.isoformat()
        hits += 1
    return hits


def _quote_targets(
    candidates: list[RadarCandidate],
    jurisdiction: str,
) -> list[str]:
    limit = (
        RADAR_NG_QUOTE_REFRESH_LIMIT
        if jurisdiction == JURISDICTION_NG
        else RADAR_US_QUOTE_REFRESH_LIMIT
    )
    missing = [
        item
        for item in candidates
        if item.price is None and (item.always_watched or item.is_catalog_member)
    ]
    missing.sort(
        key=lambda item: (
            not item.always_watched,
            _evidence_int(item, "liquidity_rank") or 9999,
            item.ticker,
        )
    )
    return [item.ticker for item in missing[:limit]]


def _estimate_quote_calls(tickers: list[str]) -> int:
    ng_count = len([ticker for ticker in tickers if ticker.endswith(".NG")])
    us_count = len(tickers) - ng_count
    us_calls = 0
    if us_count:
        us_calls = max(1, (us_count + PRICE_BATCH_SIZE - 1) // PRICE_BATCH_SIZE)
    return us_calls + ng_count


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
            source_as_of=snapshot.source_as_of or snapshot.as_of,
            carried_forward=True,
            evidence={
                **(snapshot.evidence or {}),
                "carried_forward_from_run_id": str(previous.id),
            },
            sparkline=list(snapshot.sparkline or []),
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
        evidence=candidate.evidence,
        sparkline=candidate.sparkline,
        as_of=as_of,
        source_as_of=candidate.source_as_of,
        carried_forward=candidate.carried_forward,
        stale_reason=candidate.stale_reason,
    )


async def _apply_historical_evidence(
    session: AsyncSession,
    candidates: list[RadarCandidate],
    *,
    now: datetime,
) -> None:
    if not candidates:
        return
    instruments = await _load_instruments_by_quote_symbol(
        session, {candidate.ticker for candidate in candidates}
    )
    if not instruments:
        for candidate in candidates:
            candidate.evidence["history_gap"] = "no_instrument"
        return

    candidate_by_instrument = {
        instruments[candidate.ticker].id: candidate
        for candidate in candidates
        if candidate.ticker in instruments
    }
    if not candidate_by_instrument:
        return

    cutoff = now.date() - timedelta(days=RADAR_HISTORY_LOOKBACK_DAYS)
    bars_by_instrument: dict = defaultdict(list)
    bars = await session.scalars(
        select(MarketPriceBar)
        .where(MarketPriceBar.instrument_id.in_(candidate_by_instrument.keys()))
        .where(MarketPriceBar.bar_date >= cutoff)
        .order_by(MarketPriceBar.instrument_id, MarketPriceBar.bar_date)
    )
    for bar in bars:
        bars_by_instrument[bar.instrument_id].append(bar)

    for instrument_id, candidate in candidate_by_instrument.items():
        bars_for_candidate = bars_by_instrument.get(instrument_id, [])
        if len(bars_for_candidate) < 2:
            candidate.evidence["history_gap"] = "insufficient_bars"
            if bars_for_candidate:
                candidate.sparkline = _sparkline(bars_for_candidate, candidate)
            continue

        _apply_return_evidence(candidate, bars_for_candidate)
        _apply_volume_evidence(candidate, bars_for_candidate)
        candidate.sparkline = _sparkline(bars_for_candidate, candidate)
        candidate.evidence["bar_count"] = len(bars_for_candidate)


def _apply_return_evidence(
    candidate: RadarCandidate,
    bars: list[MarketPriceBar],
) -> None:
    returns = _bar_returns(bars)
    if not returns:
        return
    mean_return = _mean(returns)
    stdev_return = _stdev(returns)
    recent_vol = _annualized_volatility(returns[-5:])
    baseline_vol = _annualized_volatility(returns)
    if baseline_vol > 0:
        candidate.evidence["realized_volatility_pct"] = _round_text(recent_vol)
        candidate.evidence["baseline_volatility_pct"] = _round_text(baseline_vol)
        candidate.evidence["volatility_ratio"] = _round_text(recent_vol / baseline_vol)

    change = _float(candidate.change_pct)
    if change is None:
        last_bar = bars[-1]
        previous_bar = bars[-2]
        change = _return_pct(previous_bar.close_price, last_bar.close_price)
        if change is not None and candidate.change_pct is None:
            candidate.change_pct = _decimal(change, "0.01")
    if change is None:
        return
    candidate.evidence["historical_return_mean_pct"] = _round_text(mean_return)
    candidate.evidence["historical_return_stdev_pct"] = _round_text(stdev_return)
    if stdev_return > 0:
        candidate.evidence["price_return_zscore"] = _round_text(
            (change - mean_return) / stdev_return
        )


def _apply_volume_evidence(
    candidate: RadarCandidate,
    bars: list[MarketPriceBar],
) -> None:
    volumes = [float(bar.volume) for bar in bars if bar.volume and bar.volume > 0]
    if not volumes:
        return
    mean_volume = _mean(volumes)
    stdev_volume = _stdev(volumes)
    candidate.avg_volume = candidate.avg_volume or int(mean_volume)
    candidate.evidence["average_volume"] = int(mean_volume)
    if candidate.volume and mean_volume > 0:
        candidate.volume_ratio = _decimal(candidate.volume / mean_volume, "0.01")
        candidate.evidence["volume_ratio"] = str(candidate.volume_ratio)
        if stdev_volume > 0:
            candidate.evidence["volume_zscore"] = _round_text(
                (float(candidate.volume) - mean_volume) / stdev_volume
            )
    if candidate.price is not None and candidate.avg_volume:
        dollar_volume = candidate.price * Decimal(candidate.avg_volume)
        candidate.evidence["avg_dollar_volume"] = _decimal_text(dollar_volume)


def _apply_sector_relative(candidates: list[RadarCandidate]) -> None:
    """Benchmark each name against its sector ETF pulse, not against peers."""
    by_ticker = {candidate.ticker: candidate for candidate in candidates}
    for candidate in candidates:
        if candidate.change_pct is None:
            continue
        if candidate.jurisdiction != JURISDICTION_US:
            continue
        benchmark_ticker = RADAR_SECTOR_BENCHMARKS.get(candidate.sector or "")
        if benchmark_ticker is None and candidate.jurisdiction == JURISDICTION_US:
            benchmark_ticker = "SPY"
        if benchmark_ticker is None or benchmark_ticker == candidate.ticker:
            continue
        benchmark = by_ticker.get(benchmark_ticker)
        if benchmark is None or benchmark.change_pct is None:
            continue
        relative = float(candidate.change_pct) - float(benchmark.change_pct)
        candidate.evidence["sector_benchmark"] = benchmark_ticker
        candidate.evidence["sector_benchmark_return_pct"] = _round_text(
            float(benchmark.change_pct)
        )
        candidate.evidence["sector_relative_return_pct"] = _round_text(relative)


async def _load_instruments_by_quote_symbol(
    session: AsyncSession,
    tickers: set[str],
) -> dict[str, Instrument]:
    if not tickers:
        return {}
    ticker_variants = set(tickers)
    ticker_variants.update(
        ticker.removesuffix(".NG") for ticker in tickers if ticker.endswith(".NG")
    )
    rows = list(
        await session.scalars(
            select(Instrument).where(Instrument.ticker.in_(ticker_variants))
        )
    )
    mapped: dict[str, Instrument] = {}
    for instrument in rows:
        if instrument.ticker in tickers:
            mapped[instrument.ticker] = instrument
    for instrument in rows:
        quote_symbol = quote_symbol_for(instrument)
        if quote_symbol in tickers and quote_symbol not in mapped:
            mapped[quote_symbol] = instrument
    return mapped


def _quote_usable_for_radar(quote: InstrumentQuote, now: datetime) -> bool:
    if quote.is_stale:
        return False
    as_of = _aware_utc(quote.as_of)
    if as_of.date() == now.date():
        return True
    return now - as_of <= timedelta(seconds=RADAR_QUOTE_CACHE_TTL_SECONDS)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _bar_returns(bars: list[MarketPriceBar]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(bars, bars[1:]):
        value = _return_pct(previous.close_price, current.close_price)
        if value is not None:
            returns.append(value)
    return returns


def _sparkline(
    bars: list[MarketPriceBar],
    candidate: RadarCandidate,
) -> list[dict[str, str]]:
    points = bars[-RADAR_SPARKLINE_POINTS:]
    sparkline = [
        {"date": bar.bar_date.isoformat(), "close": _decimal_text(bar.close_price)}
        for bar in points
    ]
    if candidate.price is not None:
        today = datetime.now(timezone.utc).date().isoformat()
        if not sparkline or sparkline[-1]["date"] != today:
            sparkline.append({"date": today, "close": _decimal_text(candidate.price)})
        else:
            sparkline[-1]["close"] = _decimal_text(candidate.price)
    return sparkline[-RADAR_SPARKLINE_POINTS:]


def _return_pct(previous: Decimal | None, current: Decimal | None) -> float | None:
    if previous is None or current is None or previous <= 0:
        return None
    return float((current - previous) / previous * Decimal("100"))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return sqrt(variance)


def _annualized_volatility(returns: list[float]) -> float:
    return _stdev(returns) * sqrt(252) if len(returns) >= 2 else 0.0


async def promote_flagged_candidates(
    session: AsyncSession,
    flagged: list[RadarCandidate],
    *,
    owner_user_id: str | None = None,
    owner_ids: list[str] | None = None,
    limit: int = 10,
) -> int:
    if owner_ids is None:
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


async def _persist_vendor_tapes(
    session: AsyncSession,
    candidates: list[RadarCandidate],
    fetched: dict[str, LiveQuote],
    *,
    now: datetime,
) -> int:
    """Store vendor tapes so the next scan can reuse quotes and build history.

    Instruments are created only for names that printed a live price this scan,
    not for the whole catalog.
    """
    tapes = dict(fetched)
    for candidate in candidates:
        if candidate.ticker in tapes or candidate.price is None:
            continue
        if candidate.source not in RADAR_VENDOR_QUOTE_SOURCES:
            continue
        tapes[candidate.ticker] = LiveQuote(
            ticker=candidate.ticker,
            price=candidate.price,
            source=candidate.source,
            as_of=candidate.source_as_of or now,
            previous_close=candidate.previous_close,
            change_pct=candidate.change_pct,
            volume=candidate.volume,
            currency=candidate.currency,
        )
    if not tapes:
        return 0

    instruments = await _ensure_instruments_for_quotes(
        session, {item.ticker: item for item in candidates}, set(tapes)
    )
    universe: dict[str, list] = {}
    for ticker, instrument in instruments.items():
        universe.setdefault(ticker, []).append(instrument.id)
    if not universe:
        return 0
    await persist_quotes(session, universe, tapes)
    return len(tapes)


async def _ensure_instruments_for_quotes(
    session: AsyncSession,
    candidates: dict[str, RadarCandidate],
    tickers: set[str],
) -> dict[str, Instrument]:
    mapped = await _load_instruments_by_quote_symbol(session, tickers)
    missing = [ticker for ticker in tickers if ticker not in mapped]
    for ticker in missing:
        candidate = candidates.get(ticker)
        if candidate is None:
            continue
        instrument = Instrument(
            ticker=ticker,
            name=(candidate.name or ticker)[:255],
            asset_class=_asset_class(candidate.asset_class),
            exchange=candidate.exchange,
            currency=candidate.currency,
            sector=candidate.sector,
            industry=candidate.industry,
        )
        session.add(instrument)
        mapped[ticker] = instrument
    if missing:
        await session.flush()
    return mapped


def _evidence_int(candidate: RadarCandidate, key: str) -> int | None:
    value = candidate.evidence.get(key)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _decimal(value: object, quantizer: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal(quantizer))
    except (InvalidOperation, ValueError):
        return None


def _round_text(value: float, places: str = "0.01") -> str:
    decimal_value = _decimal(value, places)
    return str(decimal_value if decimal_value is not None else Decimal("0"))


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
