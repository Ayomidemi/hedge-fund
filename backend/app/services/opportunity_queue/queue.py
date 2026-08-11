import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.operating_core import InstrumentResponse
from app.api.schemas.opportunity_queue import (
    OpportunityCandidateResponse,
    OpportunityCreate,
    OpportunityQueueResponse,
    OpportunityQueueSummaryResponse,
    OpportunityResponse,
    OpportunityUpdate,
)
from app.core.auth import AuthenticatedUser
from app.models import Instrument, Opportunity, TickerMemo
from app.services.administration.system_log import record_system_log
from app.services.portfolio.operating_core import upsert_instrument

logger = logging.getLogger(__name__)

STATUS_ORDER = [
    "discovered",
    "screening",
    "research",
    "watchlist",
    "candidate",
    "approved",
    "active_position",
    "exited",
    "post_mortem",
    "rejected",
]
CLOSED_STATUSES = {"exited", "post_mortem", "rejected"}
ACTIVE_STATUSES = set(STATUS_ORDER) - CLOSED_STATUSES


class OpportunityQueueError(RuntimeError):
    pass


class OpportunityNotFoundError(OpportunityQueueError):
    pass


class OpportunityValidationError(OpportunityQueueError):
    pass


async def list_opportunity_queue(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    candidate_limit: int = 12,
) -> OpportunityQueueResponse:
    opportunities = list(
        await session.scalars(
            select(Opportunity)
            .options(
                selectinload(Opportunity.instrument),
                selectinload(Opportunity.source_memo),
                selectinload(Opportunity.source_recommendation),
            )
            .where(Opportunity.owner_user_id == user.id)
            .order_by(Opportunity.updated_at.desc())
        )
    )
    opportunities = sorted(opportunities, key=_opportunity_sort_key)
    candidates = await _load_candidate_memos(
        session,
        user,
        queued_memo_ids={
            opportunity.source_memo_id
            for opportunity in opportunities
            if opportunity.source_memo_id is not None
        },
        limit=candidate_limit,
    )

    logger.info(
        "opportunity_queue_loaded",
        extra={
            "owner_user_id": user.id,
            "opportunity_count": len(opportunities),
            "candidate_count": len(candidates),
        },
    )

    return OpportunityQueueResponse(
        generated_at=datetime.now(timezone.utc),
        summary=_queue_summary(opportunities, len(candidates)),
        opportunities=[
            _opportunity_response(opportunity) for opportunity in opportunities
        ],
        candidates=[_candidate_response(memo) for memo in candidates],
        status_order=STATUS_ORDER,
    )


async def create_opportunity(
    session: AsyncSession,
    user: AuthenticatedUser,
    payload: OpportunityCreate,
) -> OpportunityResponse:
    source_memo = None
    if payload.source_memo_id is not None:
        existing = await _load_opportunity_by_source_memo(
            session, user, payload.source_memo_id
        )
        if existing is not None:
            return _opportunity_response(existing)

        source_memo = await _load_owned_memo(session, user, payload.source_memo_id)
        if source_memo is None:
            raise OpportunityValidationError("Source memo was not found.")

    if source_memo is None and payload.instrument is None:
        raise OpportunityValidationError(
            "Provide either a source memo or an instrument."
        )
    if source_memo is None and not payload.thesis:
        raise OpportunityValidationError("Manual opportunities require a thesis.")

    instrument = (
        source_memo.instrument
        if source_memo is not None
        else await upsert_instrument(session, payload.instrument)
    )
    scores = source_memo.scores if source_memo is not None else {}
    now = datetime.now(timezone.utc)
    status = payload.status
    opportunity = Opportunity(
        owner_user_id=user.id,
        instrument_id=instrument.id,
        source_memo_id=source_memo.id if source_memo is not None else None,
        source_recommendation_id=(
            source_memo.recommendation_id if source_memo is not None else None
        ),
        discovered_at=now,
        status=status,
        priority=payload.priority,
        thesis=payload.thesis or source_memo.thesis,
        research_question=payload.research_question
        or _default_research_question(instrument),
        next_action=payload.next_action or _default_next_action(status),
        time_horizon=payload.time_horizon
        or (source_memo.time_horizon if source_memo else None),
        conviction_score=payload.conviction_score
        or _decimal(scores.get("conviction_score")),
        expected_edge_pct=payload.expected_edge_pct,
        target_weight=payload.target_weight
        or _decimal(scores.get("recommended_weight")),
        review_by=payload.review_by,
        closed_at=now if status in CLOSED_STATUSES else None,
        notes=payload.notes,
        status_history=[_status_event(status, "Opportunity created.")],
    )
    session.add(opportunity)
    await session.flush()
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="opportunity",
        event="opportunity_created",
        message=f"{instrument.ticker} added to the opportunity queue ({status}).",
        context={
            "opportunity_id": str(opportunity.id),
            "ticker": instrument.ticker,
            "status": status,
        },
    )
    await session.commit()
    opportunity = await _load_opportunity(session, user, opportunity.id)
    if opportunity is None:
        raise RuntimeError("Opportunity could not be loaded after creation.")

    logger.info(
        "opportunity_created",
        extra={
            "owner_user_id": user.id,
            "opportunity_id": str(opportunity.id),
            "ticker": opportunity.instrument.ticker,
            "status": opportunity.status,
        },
    )

    return _opportunity_response(opportunity)


async def update_opportunity(
    session: AsyncSession,
    user: AuthenticatedUser,
    opportunity_id: UUID,
    payload: OpportunityUpdate,
) -> OpportunityResponse:
    opportunity = await _load_opportunity(session, user, opportunity_id)
    if opportunity is None:
        raise OpportunityNotFoundError("Opportunity was not found.")

    updates = payload.model_dump(exclude_unset=True)
    previous_status = opportunity.status
    for field_name, value in updates.items():
        if field_name == "thesis" and value is None:
            raise OpportunityValidationError("Opportunity thesis is required.")
        setattr(opportunity, field_name, value)

    if "status" in updates and updates["status"] != previous_status:
        history = list(opportunity.status_history or [])
        history.append(
            _status_event(str(updates["status"]), f"Moved from {previous_status}.")
        )
        opportunity.status_history = history

    if opportunity.status in CLOSED_STATUSES and opportunity.closed_at is None:
        opportunity.closed_at = datetime.now(timezone.utc)
    if opportunity.status not in CLOSED_STATUSES:
        opportunity.closed_at = None

    await record_system_log(
        session,
        owner_user_id=user.id,
        category="opportunity",
        event="opportunity_updated",
        message=f"{opportunity.instrument.ticker} opportunity updated to {opportunity.status}.",
        context={
            "opportunity_id": str(opportunity.id),
            "ticker": opportunity.instrument.ticker,
            "status": opportunity.status,
            "previous_status": previous_status,
        },
    )
    await session.commit()
    opportunity = await _load_opportunity(session, user, opportunity_id)
    if opportunity is None:
        raise RuntimeError("Opportunity could not be loaded after update.")

    logger.info(
        "opportunity_updated",
        extra={
            "owner_user_id": user.id,
            "opportunity_id": str(opportunity.id),
            "ticker": opportunity.instrument.ticker,
            "status": opportunity.status,
        },
    )

    return _opportunity_response(opportunity)


async def _load_opportunity(
    session: AsyncSession,
    user: AuthenticatedUser,
    opportunity_id: UUID,
) -> Opportunity | None:
    return await session.scalar(
        select(Opportunity)
        .options(
            selectinload(Opportunity.instrument),
            selectinload(Opportunity.source_memo),
            selectinload(Opportunity.source_recommendation),
        )
        .where(Opportunity.owner_user_id == user.id, Opportunity.id == opportunity_id)
    )


async def _load_opportunity_by_source_memo(
    session: AsyncSession,
    user: AuthenticatedUser,
    source_memo_id: UUID,
) -> Opportunity | None:
    return await session.scalar(
        select(Opportunity)
        .options(
            selectinload(Opportunity.instrument),
            selectinload(Opportunity.source_memo),
            selectinload(Opportunity.source_recommendation),
        )
        .where(
            Opportunity.owner_user_id == user.id,
            Opportunity.source_memo_id == source_memo_id,
        )
    )


async def _load_owned_memo(
    session: AsyncSession,
    user: AuthenticatedUser,
    memo_id: UUID,
) -> TickerMemo | None:
    return await session.scalar(
        select(TickerMemo)
        .options(selectinload(TickerMemo.instrument))
        .where(TickerMemo.owner_user_id == user.id, TickerMemo.id == memo_id)
    )


async def _load_candidate_memos(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    queued_memo_ids: set[UUID],
    limit: int,
) -> list[TickerMemo]:
    statement = (
        select(TickerMemo)
        .options(selectinload(TickerMemo.instrument))
        .where(TickerMemo.owner_user_id == user.id)
        .order_by(TickerMemo.memo_date.desc(), TickerMemo.created_at.desc())
        .limit(limit)
    )
    if queued_memo_ids:
        statement = statement.where(TickerMemo.id.not_in(queued_memo_ids))

    return list(await session.scalars(statement))


def _opportunity_response(opportunity: Opportunity) -> OpportunityResponse:
    source_scores = opportunity.source_memo.scores if opportunity.source_memo else {}
    return OpportunityResponse(
        id=opportunity.id,
        instrument=InstrumentResponse.model_validate(opportunity.instrument),
        source_memo_id=opportunity.source_memo_id,
        source_recommendation_id=opportunity.source_recommendation_id,
        discovered_at=opportunity.discovered_at,
        status=opportunity.status,
        priority=opportunity.priority,
        thesis=opportunity.thesis,
        research_question=opportunity.research_question,
        next_action=opportunity.next_action,
        time_horizon=opportunity.time_horizon,
        conviction_score=opportunity.conviction_score,
        expected_edge_pct=opportunity.expected_edge_pct,
        target_weight=opportunity.target_weight,
        review_by=opportunity.review_by,
        closed_at=opportunity.closed_at,
        notes=opportunity.notes,
        status_history=opportunity.status_history or [],
        latest_action=_optional_string(source_scores.get("action")),
        latest_composite_score=_decimal(source_scores.get("composite_score")),
        latest_confidence_score=_decimal(source_scores.get("confidence_score")),
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
    )


def _candidate_response(memo: TickerMemo) -> OpportunityCandidateResponse:
    scores = memo.scores or {}
    return OpportunityCandidateResponse(
        memo_id=memo.id,
        recommendation_id=memo.recommendation_id,
        ticker=memo.instrument.ticker,
        name=memo.instrument.name,
        asset_class=memo.instrument.asset_class,
        memo_date=memo.memo_date,
        classification=memo.classification,
        executive_view=memo.executive_view,
        action=_optional_string(scores.get("action")),
        composite_score=_decimal(scores.get("composite_score")),
        confidence_score=_decimal(scores.get("confidence_score")),
    )


def _queue_summary(
    opportunities: list[Opportunity],
    candidate_count: int,
) -> OpportunityQueueSummaryResponse:
    status_counts = {status: 0 for status in STATUS_ORDER}
    for opportunity in opportunities:
        status_counts[opportunity.status] = status_counts.get(opportunity.status, 0) + 1

    review_dates = [
        opportunity.review_by
        for opportunity in opportunities
        if opportunity.review_by is not None and opportunity.status in ACTIVE_STATUSES
    ]
    return OpportunityQueueSummaryResponse(
        total=len(opportunities),
        active=len(
            [
                opportunity
                for opportunity in opportunities
                if opportunity.status in ACTIVE_STATUSES
            ]
        ),
        high_priority=len(
            [
                opportunity
                for opportunity in opportunities
                if opportunity.priority in {"high", "urgent"}
            ]
        ),
        approved=status_counts.get("approved", 0),
        candidates=candidate_count,
        next_review_by=min(review_dates) if review_dates else None,
        status_counts=status_counts,
    )


def _opportunity_sort_key(opportunity: Opportunity) -> tuple[int, int, datetime]:
    priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
    status_order = {status: index for index, status in enumerate(STATUS_ORDER)}
    return (
        status_order.get(opportunity.status, len(status_order)),
        priority_order.get(opportunity.priority, len(priority_order)),
        opportunity.updated_at,
    )


def _status_event(status: str, note: str) -> dict:
    return {
        "status": status,
        "at": datetime.now(timezone.utc).isoformat(),
        "note": note,
    }


def _default_research_question(instrument: Instrument) -> str:
    return (
        f"What evidence would make {instrument.ticker} attractive enough to move "
        "from research into the approved candidate set?"
    )


def _default_next_action(status: str) -> str:
    if status == "approved":
        return "Run pre-trade risk check and confirm sizing before execution."
    if status == "candidate":
        return "Review risk fit, model confidence, and thesis breakers."
    if status == "watchlist":
        return "Wait for price, data, or thesis trigger before promotion."
    return "Complete research review and decide whether to promote."


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
