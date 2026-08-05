import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.operating_core import InstrumentResponse
from app.api.schemas.ticker_intelligence import (
    TickerAnalysisCreate,
    TickerAnalysisResponse,
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
    TickerMemo,
)
from app.services.portfolio.operating_core import upsert_instrument
from app.services.ticker_intelligence.scoring import score_payload, score_ticker

logger = logging.getLogger(__name__)

TICKER_MODEL_NAME = "Phase One Ticker Analyst"
TICKER_MODEL_VERSION = "0.1.0"


async def analyze_ticker(
    session: AsyncSession,
    payload: TickerAnalysisCreate,
) -> TickerAnalysisResponse:
    instrument = await upsert_instrument(session, payload.instrument)
    scorecard = score_ticker(payload.metrics, instrument.asset_class)
    model_version = await _get_or_create_model_version(session)

    recommendation = ModelRecommendation(
        model_version_id=model_version.id,
        instrument_id=instrument.id,
        generated_at=datetime.now(timezone.utc),
        action=scorecard.action,
        confidence_score=scorecard.confidence_score,
        conviction_score=scorecard.conviction_score,
        recommended_weight=scorecard.recommended_weight,
        time_horizon=payload.time_horizon,
        thesis=payload.thesis,
        scores=score_payload(scorecard),
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
        instrument_id=instrument.id,
        recommendation_id=recommendation.id,
        memo_date=payload.memo_date,
        classification=scorecard.classification,
        time_horizon=payload.time_horizon,
        executive_view=_executive_view(instrument, scorecard.action, scorecard.classification),
        thesis=payload.thesis,
        bull_case=payload.bull_case,
        base_case=payload.base_case,
        bear_case=payload.bear_case,
        thesis_breakers=payload.thesis_breakers,
        risk_assessment=payload.risk_notes,
        scores=score_payload(scorecard),
        data_timestamp=payload.data_timestamp,
        model_version_label=f"{TICKER_MODEL_NAME} {TICKER_MODEL_VERSION}",
    )
    session.add(memo)
    await session.commit()

    memo = await _load_memo(session, memo.id)
    if memo is None:
        raise RuntimeError("Ticker memo could not be loaded after commit.")

    logger.info(
        "ticker_analysis_created",
        extra={
            "ticker": instrument.ticker,
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


async def list_recent_ticker_memos(
    session: AsyncSession,
    limit: int = 12,
) -> list[TickerMemoSummaryResponse]:
    result = await session.scalars(
        select(TickerMemo)
        .options(selectinload(TickerMemo.instrument))
        .order_by(TickerMemo.memo_date.desc(), TickerMemo.created_at.desc())
        .limit(limit)
    )
    memos = list(result)

    logger.info("recent_ticker_memos_loaded", extra={"memo_count": len(memos)})

    return [_memo_summary(memo) for memo in memos]


async def list_ticker_memos(
    session: AsyncSession,
    ticker: str,
) -> list[TickerMemoResponse]:
    normalized_ticker = ticker.strip().upper()
    result = await session.scalars(
        select(TickerMemo)
        .join(TickerMemo.instrument)
        .options(selectinload(TickerMemo.instrument))
        .where(Instrument.ticker == normalized_ticker)
        .order_by(TickerMemo.memo_date.desc(), TickerMemo.created_at.desc())
    )
    memos = list(result)

    logger.info(
        "ticker_memos_loaded",
        extra={"ticker": normalized_ticker, "memo_count": len(memos)},
    )

    return [_memo_response(memo) for memo in memos]


async def get_ticker_memo(
    session: AsyncSession,
    memo_id: UUID,
) -> TickerMemoResponse | None:
    memo = await _load_memo(session, memo_id)
    if memo is None:
        logger.info("ticker_memo_not_found", extra={"memo_id": str(memo_id)})
        return None

    logger.info(
        "ticker_memo_loaded",
        extra={"memo_id": str(memo.id), "ticker": memo.instrument.ticker},
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
            "momentum": ["price_vs_200d_pct", "relative_strength_6m_pct", "volatility_30d_pct"],
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
        extra={"model_name": model_version.name, "model_version": model_version.version},
    )

    return model_version


async def _load_memo(session: AsyncSession, memo_id) -> TickerMemo | None:
    return await session.scalar(
        select(TickerMemo)
        .options(selectinload(TickerMemo.instrument))
        .where(TickerMemo.id == memo_id)
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
