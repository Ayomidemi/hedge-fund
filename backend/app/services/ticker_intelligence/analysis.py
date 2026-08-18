import logging
from datetime import datetime, timezone
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
    TickerDeskNews,
    TickerDeskOpportunity,
    TickerDeskPosition,
    TickerDeskPreTrade,
    TickerDeskRadar,
    TickerDeskResponse,
    TickerMemoResponse,
    TickerMemoSummaryResponse,
    TickerScoreResponse,
)
from app.models import (
    EvidenceSnapshot,
    EvidenceSourceType,
    Instrument,
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
)
from app.services.administration.system_log import record_system_log
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
    memos: list[TickerMemo] = []
    if instrument is not None:
        opportunity = await _load_desk_opportunity(session, user.id, instrument.id)
        position = await _load_desk_position(session, user.id, instrument.id)
        memos = await _load_desk_memos(session, user.id, instrument.id)

    news = await _load_desk_news(session, variants)
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
        on_watchlist=watchlist is not None,
        radar=(
            TickerDeskRadar(
                change_pct=snapshot.change_pct,
                scan_state=(
                    str(evidence["scan_state"]) if evidence.get("scan_state") else None
                ),
                scan_delta_change_pct=(
                    str(evidence["scan_delta_change_pct"])
                    if evidence.get("scan_delta_change_pct") is not None
                    else None
                ),
                as_of=snapshot.source_as_of or snapshot.as_of,
            )
            if snapshot is not None
            else None
        ),
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
        news=(
            TickerDeskNews(
                id=news.id,
                title=news.title,
                source_name=news.source_name,
                published_at=news.published_at,
                event_type=news.event_type,
            )
            if news is not None
            else None
        ),
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
        memos=[_memo_summary(memo) for memo in memos],
    )


def ticker_variants(ticker: str) -> set[str]:
    normalized = ticker.strip().upper()
    if not normalized:
        return set()
    base = normalized.removesuffix(".NG")
    return {normalized, base, f"{base}.NG"}


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


async def _load_desk_news(session: AsyncSession, variants: set[str]) -> NewsItem | None:
    if not variants:
        return None
    return await session.scalar(
        select(NewsItem)
        .join(NewsTickerLink)
        .where(NewsTickerLink.ticker.in_(variants))
        .order_by(NewsItem.published_at.desc().nullslast(), NewsItem.created_at.desc())
        .limit(1)
    )


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
