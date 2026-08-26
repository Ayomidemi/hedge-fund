import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import AuthenticatedUser
from app.api.schemas.operating_core import InstrumentResponse
from app.api.schemas.ticker_intelligence import (
    TickerAnalysisCreate,
    TickerAnalysisResponse,
    TickerDeskDecisionSnapshot,
    TickerDeskNews,
    TickerDeskOpportunity,
    TickerDeskPosition,
    TickerDeskPreTrade,
    TickerDeskRadar,
    TickerDeskResponse,
    TickerDeskTriage,
    TickerMemoResponse,
    TickerMemoSummaryResponse,
    TickerScoreResponse,
)
from app.models import (
    EvidenceSnapshot,
    EvidenceSourceType,
    Instrument,
    InstrumentQuote,
    ModelRecommendation,
    ModelVersion,
    NewsItem,
    NewsTickerLink,
    Opportunity,
    Portfolio,
    Position,
    PreTradeRiskCheck,
    RadarSnapshot,
    RadarWatchlistItem,
    TickerMemo,
    TickerTriageRun,
)
from app.services.administration.system_log import record_system_log
from app.services.market_data.ingestion import persist_quotes
from app.services.market_data.quote_provider import LiveQuote, fetch_quotes
from app.services.market_data.universe import quote_symbol_for
from app.services.portfolio.operating_core import upsert_instrument
from app.services.ticker_intelligence.ml_training import (
    build_ticker_ml_report,
    save_ticker_feature_snapshot,
)
from app.services.ticker_intelligence.scoring import score_payload, score_ticker

logger = logging.getLogger(__name__)

TICKER_MODEL_NAME = "Phase One Ticker Analyst"
TICKER_MODEL_VERSION = "0.1.0"
CLOSED_OPPORTUNITY_STATUSES = {"exited", "post_mortem", "rejected"}


async def analyze_ticker(
    session: AsyncSession,
    payload: TickerAnalysisCreate,
    user: AuthenticatedUser,
) -> TickerAnalysisResponse:
    instrument = await upsert_instrument(session, payload.instrument)
    scorecard = score_ticker(payload.metrics, instrument.asset_class)
    score_data = score_payload(scorecard)
    await save_ticker_feature_snapshot(session, instrument, payload, score_data)
    await session.flush()
    score_data["ml_report"] = await _ml_report_snapshot(
        session, instrument.ticker, user
    )
    model_version = await _get_or_create_model_version(session)

    recommendation = ModelRecommendation(
        owner_user_id=user.id,
        model_version_id=model_version.id,
        instrument_id=instrument.id,
        generated_at=datetime.now(timezone.utc),
        action=scorecard.action,
        confidence_score=scorecard.confidence_score,
        conviction_score=scorecard.conviction_score,
        recommended_weight=scorecard.recommended_weight,
        time_horizon=payload.time_horizon,
        thesis=payload.thesis,
        scores=score_data,
        evidence_summary=scorecard.evidence_summary,
    )
    session.add(recommendation)
    await session.flush()

    session.add(
        EvidenceSnapshot(
            recommendation_id=recommendation.id,
            captured_at=payload.data_timestamp,
            source_type=EvidenceSourceType.MANUAL_RESEARCH.value,
            source_name="Ticker analyst manual entry",
            source_reference=payload.source_reference,
            as_of_date=payload.memo_date,
            payload=_evidence_payload(payload),
            data_version="manual-v1",
        )
    )

    memo = TickerMemo(
        owner_user_id=user.id,
        instrument_id=instrument.id,
        recommendation_id=recommendation.id,
        memo_date=payload.memo_date,
        classification=scorecard.classification,
        time_horizon=payload.time_horizon,
        executive_view=_executive_view(
            instrument, scorecard.action, scorecard.classification
        ),
        thesis=payload.thesis,
        bull_case=payload.bull_case,
        base_case=payload.base_case,
        bear_case=payload.bear_case,
        thesis_breakers=payload.thesis_breakers,
        risk_assessment=payload.risk_notes,
        scores=score_data,
        data_timestamp=payload.data_timestamp,
        model_version_label=f"{TICKER_MODEL_NAME} {TICKER_MODEL_VERSION}",
    )
    session.add(memo)
    await session.flush()
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="research",
        event="ticker_analyzed",
        message=f"{instrument.ticker} analyzed — {scorecard.classification} ({scorecard.action}).",
        context={
            "ticker": instrument.ticker,
            "memo_id": str(memo.id),
            "action": scorecard.action,
            "composite_score": str(scorecard.composite_score),
        },
    )
    await session.commit()

    memo = await _load_memo(session, memo.id, user)
    if memo is None:
        raise RuntimeError("Ticker memo could not be loaded after commit.")

    logger.info(
        "ticker_analysis_created",
        extra={
            "ticker": instrument.ticker,
            "owner_user_id": user.id,
            "memo_id": str(memo.id),
            "recommendation_id": str(recommendation.id),
            "action": scorecard.action,
            "composite_score": str(scorecard.composite_score),
            "confidence_score": str(scorecard.confidence_score),
        },
    )

    return TickerAnalysisResponse(
        memo=_memo_response(memo),
        action=scorecard.action,
        confidence_score=scorecard.confidence_score,
        conviction_score=scorecard.conviction_score,
        recommended_weight=scorecard.recommended_weight,
        composite_score=scorecard.composite_score,
        classification=scorecard.classification,
        scorecard=[
            TickerScoreResponse(
                name=score.name,
                score=score.score,
                weight=score.weight,
                notes=score.notes,
            )
            for score in scorecard.scores
        ],
        evidence_summary=scorecard.evidence_summary,
    )


async def _ml_report_snapshot(
    session: AsyncSession,
    ticker: str,
    user: AuthenticatedUser,
) -> dict:
    try:
        report = await build_ticker_ml_report(session, ticker, user=user)
        snapshot = report.model_dump(mode="json")
        snapshot.pop("model_comparison", None)
        return snapshot
    except Exception as exc:  # pragma: no cover - defensive audit preservation
        logger.warning(
            "ticker_ml_report_snapshot_failed",
            extra={"ticker": ticker, "owner_user_id": user.id, "error": str(exc)},
            exc_info=True,
        )
        return {
            "ticker": ticker,
            "comparative": None,
            "prediction": None,
            "portfolio_fit": None,
            "warnings": ["ML report could not be generated at save time."],
        }


async def list_recent_ticker_memos(
    session: AsyncSession,
    user: AuthenticatedUser,
    limit: int = 12,
) -> list[TickerMemoSummaryResponse]:
    result = await session.scalars(
        select(TickerMemo)
        .options(selectinload(TickerMemo.instrument))
        .where(TickerMemo.owner_user_id == user.id)
        .order_by(TickerMemo.memo_date.desc(), TickerMemo.created_at.desc())
        .limit(limit)
    )
    memos = list(result)

    logger.info(
        "recent_ticker_memos_loaded",
        extra={"owner_user_id": user.id, "memo_count": len(memos)},
    )

    return [_memo_summary(memo) for memo in memos]


async def list_ticker_memos(
    session: AsyncSession,
    ticker: str,
    user: AuthenticatedUser,
) -> list[TickerMemoResponse]:
    normalized_ticker = ticker.strip().upper()
    result = await session.scalars(
        select(TickerMemo)
        .join(TickerMemo.instrument)
        .options(selectinload(TickerMemo.instrument))
        .where(
            TickerMemo.owner_user_id == user.id,
            Instrument.ticker == normalized_ticker,
        )
        .order_by(TickerMemo.memo_date.desc(), TickerMemo.created_at.desc())
    )
    memos = list(result)

    logger.info(
        "ticker_memos_loaded",
        extra={
            "ticker": normalized_ticker,
            "owner_user_id": user.id,
            "memo_count": len(memos),
        },
    )

    return [_memo_response(memo) for memo in memos]


async def get_ticker_desk(
    session: AsyncSession,
    ticker: str,
    user: AuthenticatedUser,
) -> TickerDeskResponse:
    variants = ticker_variants(ticker)
    requested = ticker.strip().upper()
    instrument = await _load_desk_instrument(session, variants, requested)
    display_ticker = quote_symbol_for(instrument) if instrument is not None else requested
    snapshot = await _load_desk_radar(session, variants, display_ticker)
    watchlist = await session.scalar(
        select(RadarWatchlistItem.id)
        .where(RadarWatchlistItem.owner_user_id == user.id)
        .where(RadarWatchlistItem.ticker.in_(variants))
        .limit(1)
    )
    opportunity = None
    position = None
    latest_triage = None
    memos: list[TickerMemo] = []
    if instrument is not None:
        opportunity = await _load_desk_opportunity(session, user.id, instrument.id)
        position = await _load_desk_position(session, user.id, instrument.id)
        latest_triage = await _load_latest_triage(session, user.id, instrument.id)
        memos = await _load_desk_memos(session, user.id, instrument.id)

    news_headlines = await _load_desk_news_headlines(session, variants, limit=24)
    news = news_headlines[0] if news_headlines else None
    pre_trade = await _load_desk_pre_trade(session, user.id, variants)

    logger.info(
        "ticker_desk_loaded",
        extra={
            "ticker": display_ticker,
            "owner_user_id": user.id,
            "memo_count": len(memos),
            "on_watchlist": watchlist is not None,
        },
    )

    evidence = dict(snapshot.evidence or {}) if snapshot is not None else {}
    live_quote = await _ensure_desk_live_quote(
        session,
        ticker=display_ticker,
        instrument=instrument,
    )
    decision_snapshot = _build_decision_snapshot(
        latest_triage=latest_triage,
        position=position,
        opportunity=opportunity,
        watchlist_id=watchlist,
        radar_snapshot=snapshot,
        radar_evidence=evidence,
        pre_trade=pre_trade,
        news=news,
        memo_count=len(memos),
    )
    radar = _desk_radar_payload(snapshot, evidence, live_quote, display_ticker)
    return TickerDeskResponse(
        ticker=display_ticker,
        name=(
            instrument.name
            if instrument is not None
            else (snapshot.name if snapshot is not None else display_ticker)
        ),
        asset_class=(
            instrument.asset_class
            if instrument is not None
            else (snapshot.asset_class if snapshot is not None else "equity")
        ),
        exchange=(
            instrument.exchange
            if instrument is not None
            else (snapshot.exchange if snapshot is not None else None)
        ),
        jurisdiction=(
            snapshot.jurisdiction
            if snapshot is not None
            else (
                "NG"
                if display_ticker.endswith(".NG")
                else ("US" if instrument is not None else None)
            )
        ),
        on_watchlist=watchlist is not None,
        in_portfolio=position is not None,
        radar=radar,
        opportunity=(
            TickerDeskOpportunity(
                id=opportunity.id,
                status=opportunity.status,
                priority=opportunity.priority,
                source_memo_id=opportunity.source_memo_id,
            )
            if opportunity is not None
            else None
        ),
        news=_desk_news_item(news) if news is not None else None,
        recent_headlines=[_desk_news_item(item) for item in news_headlines],
        pre_trade=(
            TickerDeskPreTrade(
                id=pre_trade.id,
                decision=pre_trade.decision,
                risk_level=pre_trade.risk_level,
                checked_at=pre_trade.checked_at,
            )
            if pre_trade is not None
            else None
        ),
        position=(
            TickerDeskPosition(
                quantity=position.quantity,
                average_cost=position.average_cost,
            )
            if position is not None
            else None
        ),
        latest_triage=(
            TickerDeskTriage(
                id=latest_triage.id,
                generated_at=latest_triage.generated_at,
                research_priority=latest_triage.research_priority,
                initial_view=latest_triage.initial_view,
                triage_decision=latest_triage.triage_decision,
                action_label=latest_triage.action_label,
                confidence_score=latest_triage.confidence_score,
                composite_score=latest_triage.composite_score,
                recommended_weight=latest_triage.recommended_weight,
                next_action=latest_triage.next_action,
            )
            if latest_triage is not None
            else None
        ),
        decision_snapshot=decision_snapshot,
        memos=[_memo_summary(memo) for memo in memos],
    )


def ticker_variants(ticker: str) -> set[str]:
    normalized = ticker.strip().upper()
    if not normalized:
        return set()
    base = normalized.removesuffix(".NG")
    return {normalized, base, f"{base}.NG"}


DESK_QUOTE_MAX_AGE = timedelta(seconds=90)


async def _ensure_desk_live_quote(
    session: AsyncSession,
    *,
    ticker: str,
    instrument: Instrument | None,
) -> LiveQuote | None:
    """Return a fresh-enough live quote for the ticker hub, fetching if needed."""
    variants = ticker_variants(ticker)
    cached = await session.scalar(
        select(InstrumentQuote)
        .join(Instrument, Instrument.id == InstrumentQuote.instrument_id)
        .where(Instrument.ticker.in_(variants))
        .where(InstrumentQuote.is_stale.is_(False))
        .order_by(InstrumentQuote.as_of.desc())
        .limit(1)
    )
    now = datetime.now(timezone.utc)
    if (
        cached is not None
        and cached.as_of is not None
        and now - cached.as_of <= DESK_QUOTE_MAX_AGE
    ):
        return LiveQuote(
            ticker=ticker,
            price=cached.price,
            source=cached.source,
            as_of=cached.as_of,
            previous_close=cached.previous_close,
            change_pct=cached.change_pct,
            day_open=cached.day_open,
            day_high=cached.day_high,
            day_low=cached.day_low,
            volume=cached.volume,
            currency=cached.currency,
        )

    try:
        fetched = await fetch_quotes([ticker])
    except Exception:  # noqa: BLE001
        logger.exception("desk_live_quote_fetch_failed", extra={"ticker": ticker})
        fetched = {}

    live = fetched.get(ticker) or next(iter(fetched.values()), None)
    if live is not None and instrument is not None:
        try:
            await persist_quotes(
                session,
                {live.ticker: [instrument.id]},
                {live.ticker: live},
                mark_missing_stale=False,
            )
            await session.flush()
        except Exception:  # noqa: BLE001
            logger.exception(
                "desk_live_quote_persist_failed",
                extra={"ticker": live.ticker},
            )

    if live is not None:
        return live
    if cached is None:
        return None
    return LiveQuote(
        ticker=ticker,
        price=cached.price,
        source=cached.source,
        as_of=cached.as_of,
        previous_close=cached.previous_close,
        change_pct=cached.change_pct,
        currency=cached.currency,
    )


def _desk_radar_payload(
    snapshot: RadarSnapshot | None,
    evidence: dict,
    live_quote: LiveQuote | None,
    display_ticker: str,
) -> TickerDeskRadar | None:
    if snapshot is None and live_quote is None:
        return None
    return TickerDeskRadar(
        change_pct=(
            live_quote.change_pct
            if live_quote is not None and live_quote.change_pct is not None
            else (snapshot.change_pct if snapshot is not None else None)
        ),
        scan_state=(
            str(evidence["scan_state"]) if evidence.get("scan_state") else None
        ),
        scan_delta_change_pct=(
            str(evidence["scan_delta_change_pct"])
            if evidence.get("scan_delta_change_pct") is not None
            else None
        ),
        as_of=(
            live_quote.as_of
            if live_quote is not None
            else (
                snapshot.source_as_of or snapshot.as_of
                if snapshot is not None
                else None
            )
        ),
        price=(
            live_quote.price
            if live_quote is not None
            else (snapshot.price if snapshot is not None else None)
        ),
        jurisdiction=(
            snapshot.jurisdiction
            if snapshot is not None
            else ("NG" if display_ticker.endswith(".NG") else "US")
        ),
        sector=snapshot.sector if snapshot is not None else None,
        industry=snapshot.industry if snapshot is not None else None,
        flags=list(snapshot.flags or []) if snapshot is not None else [],
        radar_priority=(
            (snapshot.radar_priority or evidence.get("radar_priority"))
            if snapshot is not None
            else None
        ),
        move_scope=_text(evidence.get("move_scope")),
        industry_status=_text(evidence.get("industry_status")),
        price_return_zscore=_text(evidence.get("price_return_zscore")),
        sector_relative_return_pct=_text(evidence.get("sector_relative_return_pct")),
        volume_ratio=snapshot.volume_ratio if snapshot is not None else None,
    )


def _build_decision_snapshot(
    *,
    latest_triage: TickerTriageRun | None,
    position: Position | None,
    opportunity: Opportunity | None,
    watchlist_id,
    radar_snapshot: RadarSnapshot | None,
    radar_evidence: dict,
    pre_trade: PreTradeRiskCheck | None,
    news: NewsItem | None,
    memo_count: int,
) -> TickerDeskDecisionSnapshot:
    has_position = position is not None
    position_context = "owned" if has_position else "not_owned"
    blockers = _decision_blockers(
        latest_triage=latest_triage,
        has_position=has_position,
        radar_snapshot=radar_snapshot,
        radar_evidence=radar_evidence,
        pre_trade=pre_trade,
    )

    if latest_triage is None:
        return TickerDeskDecisionSnapshot(
            action="run_triage",
            action_label="Run Quick Triage",
            stance="pending",
            summary="No saved quick screen yet.",
            position_context=position_context,
            blockers=blockers or ["No persisted Quick Triage decision."],
            next_step="Run Quick Triage before making a research or capital decision.",
        )

    action, action_label, stance = _decision_action(
        latest_triage,
        has_position=has_position,
        blockers=blockers,
    )
    context_note = _decision_context_note(
        has_position=has_position,
        opportunity=opportunity,
        watchlist_id=watchlist_id,
        news=news,
        memo_count=memo_count,
    )
    summary = f"{latest_triage.next_action} {context_note}".strip()

    return TickerDeskDecisionSnapshot(
        action=action,
        action_label=action_label,
        stance=stance,
        summary=summary,
        confidence_score=latest_triage.confidence_score,
        composite_score=latest_triage.composite_score,
        recommended_weight=latest_triage.recommended_weight,
        source_generated_at=latest_triage.generated_at,
        position_context=position_context,
        blockers=blockers,
        next_step=_decision_next_step(action, latest_triage, has_position=has_position),
    )


def _decision_action(
    latest_triage: TickerTriageRun,
    *,
    has_position: bool,
    blockers: list[str],
) -> tuple[str, str, str]:
    decision = latest_triage.triage_decision.strip().lower()
    confidence = latest_triage.confidence_score
    composite = latest_triage.composite_score
    has_risk_blocker = any(_is_risk_blocker(blocker) for blocker in blockers)

    if has_position:
        if decision == "reject" or has_risk_blocker:
            return "review_position", "Review Position", "risk"
        return "hold", "Hold", "constructive" if composite >= Decimal("60") else "neutral"

    if decision == "research" and confidence >= Decimal("50"):
        return "buy_candidate", "Buy Candidate", "constructive"
    if decision == "reject":
        return "avoid", "Avoid", "negative"
    return "watch", "Watch", "neutral"


def _decision_blockers(
    *,
    latest_triage: TickerTriageRun | None,
    has_position: bool,
    radar_snapshot: RadarSnapshot | None,
    radar_evidence: dict,
    pre_trade: PreTradeRiskCheck | None,
) -> list[str]:
    blockers: list[str] = []
    if latest_triage is not None and latest_triage.confidence_score < Decimal("45"):
        blockers.append("Low triage confidence.")

    if pre_trade is not None:
        decision = pre_trade.decision.strip().lower()
        risk_level = pre_trade.risk_level.strip().lower()
        if decision in {"reject", "reduce_or_review"}:
            blockers.append(f"Risk Centre pre-trade decision is {decision}.")
        elif risk_level in {"halt", "reduce", "suspend", "defensive"}:
            blockers.append(f"Risk Centre risk level is {risk_level}.")

    change_pct = radar_snapshot.change_pct if radar_snapshot is not None else None
    scan_state = str(radar_evidence.get("scan_state") or "").strip().lower()
    if has_position and change_pct is not None and change_pct <= Decimal("-3"):
        blockers.append(f"Position is down {change_pct}% on the latest radar print.")
    elif has_position and scan_state in {"falling", "lurching_down", "selloff"}:
        blockers.append(f"Market Radar state is {scan_state.replace('_', ' ')}.")

    return list(dict.fromkeys(blockers))


def _decision_context_note(
    *,
    has_position: bool,
    opportunity: Opportunity | None,
    watchlist_id,
    news: NewsItem | None,
    memo_count: int,
) -> str:
    if has_position:
        return "Existing position context applies."
    if opportunity is not None and opportunity.status not in CLOSED_OPPORTUNITY_STATUSES:
        return f"Current queue status: {opportunity.status}."
    if watchlist_id is not None:
        return "Ticker is already on the radar watchlist."
    if news is not None:
        return "Latest stored news is available on the desk."
    if memo_count > 0:
        return "Past research memo exists."
    return ""


def _decision_next_step(
    action: str,
    latest_triage: TickerTriageRun,
    *,
    has_position: bool,
) -> str:
    if action == "buy_candidate":
        return "Open deep research, then move to Opportunity Queue if the thesis survives."
    if action == "hold":
        return "Keep monitoring; refresh triage when price, news, or thesis changes."
    if action == "watch":
        return "Keep or add to watchlist; wait for stronger evidence."
    if action == "avoid":
        return "Do not spend more research time unless new evidence changes the setup."
    if action == "review_position":
        return "Open Risk Centre before adding, trimming, or exiting."
    if has_position:
        return "Review the position with Risk Centre context."
    return latest_triage.next_action


def _is_risk_blocker(blocker: str) -> bool:
    normalized = blocker.strip().lower()
    return (
        "risk centre" in normalized
        or "position is down" in normalized
        or "market radar state" in normalized
    )


async def _load_desk_instrument(
    session: AsyncSession, variants: set[str], requested: str
) -> Instrument | None:
    if not variants:
        return None
    instruments = list(
        await session.scalars(select(Instrument).where(Instrument.ticker.in_(variants)))
    )
    if not instruments:
        return None
    exact = next(
        (row for row in instruments if row.ticker.upper() == requested), None
    )
    return exact or instruments[0]


async def _load_desk_radar(
    session: AsyncSession, variants: set[str], preferred: str
) -> RadarSnapshot | None:
    if not variants:
        return None
    snapshots = list(
        await session.scalars(
            select(RadarSnapshot)
            .where(RadarSnapshot.ticker.in_(variants))
            .distinct(RadarSnapshot.ticker)
            .order_by(RadarSnapshot.ticker, RadarSnapshot.as_of.desc())
        )
    )
    if not snapshots:
        return None
    by_ticker = {row.ticker.upper(): row for row in snapshots}
    return (
        by_ticker.get(preferred.upper())
        or by_ticker.get(preferred.upper().removesuffix(".NG"))
        or snapshots[0]
    )


async def _load_desk_opportunity(
    session: AsyncSession, owner_user_id: str, instrument_id
) -> Opportunity | None:
    opportunities = list(
        await session.scalars(
            select(Opportunity)
            .where(Opportunity.owner_user_id == owner_user_id)
            .where(Opportunity.instrument_id == instrument_id)
            .order_by(Opportunity.updated_at.desc())
        )
    )
    if not opportunities:
        return None
    open_rows = [
        row for row in opportunities if row.status not in CLOSED_OPPORTUNITY_STATUSES
    ]
    return open_rows[0] if open_rows else opportunities[0]


async def _load_desk_position(
    session: AsyncSession, owner_user_id: str, instrument_id
) -> Position | None:
    return await session.scalar(
        select(Position)
        .join(Portfolio, Portfolio.id == Position.portfolio_id)
        .where(Portfolio.owner_user_id == owner_user_id)
        .where(Position.instrument_id == instrument_id)
        .where(Position.quantity > 0)
        .where(Position.closed_at.is_(None))
    )


async def _load_latest_triage(
    session: AsyncSession, owner_user_id: str, instrument_id
) -> TickerTriageRun | None:
    return await session.scalar(
        select(TickerTriageRun)
        .where(TickerTriageRun.owner_user_id == owner_user_id)
        .where(TickerTriageRun.instrument_id == instrument_id)
        .order_by(
            TickerTriageRun.generated_at.desc(),
            TickerTriageRun.created_at.desc(),
        )
        .limit(1)
    )


async def _load_desk_memos(
    session: AsyncSession, owner_user_id: str, instrument_id
) -> list[TickerMemo]:
    return list(
        await session.scalars(
            select(TickerMemo)
            .options(selectinload(TickerMemo.instrument))
            .where(TickerMemo.owner_user_id == owner_user_id)
            .where(TickerMemo.instrument_id == instrument_id)
            .order_by(TickerMemo.memo_date.desc(), TickerMemo.created_at.desc())
        )
    )


async def _load_desk_news_headlines(
    session: AsyncSession, variants: set[str], *, limit: int = 8
) -> list[NewsItem]:
    if not variants:
        return []
    return list(
        await session.scalars(
            select(NewsItem)
            .join(NewsTickerLink)
            .where(NewsTickerLink.ticker.in_(variants))
            .order_by(
                NewsItem.published_at.desc().nullslast(),
                NewsItem.created_at.desc(),
            )
            .limit(limit)
            .distinct()
        )
    )


def _desk_news_item(item: NewsItem) -> TickerDeskNews:
    return TickerDeskNews(
        id=item.id,
        title=item.title,
        source_name=item.source_name,
        published_at=item.published_at,
        event_type=item.event_type,
        url=item.url,
    )


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


async def _load_desk_news(session: AsyncSession, variants: set[str]) -> NewsItem | None:
    headlines = await _load_desk_news_headlines(session, variants, limit=1)
    return headlines[0] if headlines else None


async def _load_desk_pre_trade(
    session: AsyncSession, owner_user_id: str, variants: set[str]
) -> PreTradeRiskCheck | None:
    if not variants:
        return None
    checks = list(
        await session.scalars(
            select(PreTradeRiskCheck)
            .where(PreTradeRiskCheck.owner_user_id == owner_user_id)
            .order_by(PreTradeRiskCheck.checked_at.desc())
            .limit(80)
        )
    )
    for check in checks:
        payload = check.request_payload or {}
        instrument = payload.get("instrument") or {}
        ticker = str(instrument.get("ticker") or "").upper()
        if ticker in variants:
            return check
    return None


async def get_ticker_memo(
    session: AsyncSession,
    memo_id: UUID,
    user: AuthenticatedUser,
) -> TickerMemoResponse | None:
    memo = await _load_memo(session, memo_id, user)
    if memo is None:
        logger.info(
            "ticker_memo_not_found",
            extra={"memo_id": str(memo_id), "owner_user_id": user.id},
        )
        return None

    logger.info(
        "ticker_memo_loaded",
        extra={
            "memo_id": str(memo.id),
            "owner_user_id": user.id,
            "ticker": memo.instrument.ticker,
        },
    )
    return _memo_response(memo)


async def _get_or_create_model_version(session: AsyncSession) -> ModelVersion:
    model_version = await session.scalar(
        select(ModelVersion).where(
            ModelVersion.name == TICKER_MODEL_NAME,
            ModelVersion.version == TICKER_MODEL_VERSION,
        )
    )
    if model_version is not None:
        return model_version

    model_version = ModelVersion(
        name=TICKER_MODEL_NAME,
        version=TICKER_MODEL_VERSION,
        pod="Fundamental Equity Pod",
        purpose="Manual first-pass ticker scoring for phase-one research.",
        training_data={
            "source": "manual_entry",
            "note": "No statistical training set yet.",
        },
        features={
            "quality": ["net_margin_pct", "free_cash_flow_yield_pct", "debt_to_equity"],
            "growth": ["revenue_growth_pct", "earnings_growth_pct"],
            "valuation": ["pe_ratio", "forward_pe", "free_cash_flow_yield_pct"],
            "momentum": [
                "price_vs_200d_pct",
                "relative_strength_6m_pct",
                "volatility_30d_pct",
            ],
            "risk": ["debt_to_equity", "volatility_30d_pct"],
        },
        metrics={"validation": "deterministic_rule_set"},
        assumptions="Manual metrics are trusted as entered and must be source-checked by the reviewer.",
        limitations="Not a live market-data model. Scores are provisional when input data is sparse.",
        approved_use="Research triage, watchlist construction, and memo drafting.",
        prohibited_use="Unsupervised trade execution or position sizing without risk review.",
        shutdown_criteria="Disable if scoring conflicts repeatedly with reviewed evidence or stale data.",
    )
    session.add(model_version)
    await session.flush()

    logger.info(
        "ticker_model_version_seeded",
        extra={
            "model_name": model_version.name,
            "model_version": model_version.version,
        },
    )

    return model_version


async def _load_memo(
    session: AsyncSession,
    memo_id,
    user: AuthenticatedUser,
) -> TickerMemo | None:
    return await session.scalar(
        select(TickerMemo)
        .options(selectinload(TickerMemo.instrument))
        .where(TickerMemo.id == memo_id, TickerMemo.owner_user_id == user.id)
    )


def _memo_response(memo: TickerMemo) -> TickerMemoResponse:
    return TickerMemoResponse(
        id=memo.id,
        instrument=InstrumentResponse.model_validate(memo.instrument),
        recommendation_id=memo.recommendation_id,
        memo_date=memo.memo_date,
        classification=memo.classification,
        time_horizon=memo.time_horizon,
        executive_view=memo.executive_view,
        thesis=memo.thesis,
        bull_case=memo.bull_case,
        base_case=memo.base_case,
        bear_case=memo.bear_case,
        thesis_breakers=memo.thesis_breakers,
        risk_assessment=memo.risk_assessment,
        scores=memo.scores,
        data_timestamp=memo.data_timestamp,
        model_version_label=memo.model_version_label,
    )


def _memo_summary(memo: TickerMemo) -> TickerMemoSummaryResponse:
    scores = memo.scores or {}
    return TickerMemoSummaryResponse(
        id=memo.id,
        ticker=memo.instrument.ticker,
        name=memo.instrument.name,
        asset_class=memo.instrument.asset_class,
        memo_date=memo.memo_date,
        classification=memo.classification,
        executive_view=memo.executive_view,
        composite_score=_optional_decimal(scores.get("composite_score")),
        action=_optional_string(scores.get("action")),
        confidence_score=_optional_decimal(scores.get("confidence_score")),
    )


def _evidence_payload(payload: TickerAnalysisCreate) -> dict:
    return {
        "instrument": payload.instrument.model_dump(mode="json"),
        "metrics": payload.metrics.model_dump(mode="json"),
        "investment_question": payload.investment_question,
        "thesis": payload.thesis,
        "bull_case": payload.bull_case,
        "base_case": payload.base_case,
        "bear_case": payload.bear_case,
        "thesis_breakers": payload.thesis_breakers,
        "risk_notes": payload.risk_notes,
    }


def _executive_view(instrument: Instrument, action: str, classification: str) -> str:
    return (
        f"{instrument.ticker} is classified as {classification}. "
        f"Current process action: {action}."
    )


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
