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
    OpportunityLinks,
    OpportunityMemoLink,
    OpportunityPositionLink,
    OpportunityQueueResponse,
    OpportunityQueueSummaryResponse,
    OpportunityRadarLink,
    OpportunityResponse,
    OpportunityRiskLink,
    OpportunityTradeLink,
    OpportunityUpdate,
)
from app.core.auth import AuthenticatedUser
from app.models import (
    Instrument,
    Opportunity,
    Portfolio,
    Position,
    PreTradeRiskCheck,
    RadarSnapshot,
    TickerMemo,
    Trade,
)
from app.services.administration.system_log import record_system_log
from app.services.market_data.universe import quote_symbol_for
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
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
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
    filtered = [
        opportunity
        for opportunity in opportunities
        if status in {None, "", "all"} or opportunity.status == status
    ]
    page, page_size, total, total_pages, paged = _paginate(filtered, page, page_size)
    links_by_id = await _load_links(session, user, paged)
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
            "page": page,
            "candidate_count": len(candidates),
        },
    )

    return OpportunityQueueResponse(
        generated_at=datetime.now(timezone.utc),
        summary=_queue_summary(opportunities, len(candidates)),
        opportunities=[
            _opportunity_response(opportunity, links_by_id.get(opportunity.id))
            for opportunity in paged
        ],
        candidates=[_candidate_response(memo) for memo in candidates],
        status_order=STATUS_ORDER,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
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

    links = await _load_links(session, user, [opportunity])
    logger.info(
        "opportunity_created",
        extra={
            "owner_user_id": user.id,
            "opportunity_id": str(opportunity.id),
            "ticker": opportunity.instrument.ticker,
            "status": opportunity.status,
        },
    )

    return _opportunity_response(opportunity, links.get(opportunity.id))


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
    override_reason = updates.pop("override_reason", None)
    previous_status = opportunity.status
    proposed_status = updates.get("status", previous_status)

    if proposed_status != previous_status:
        links = await _load_links(session, user, [opportunity])
        error = status_gate_error(
            proposed_status,
            thesis=updates.get("thesis", opportunity.thesis),
            research_question=updates.get("research_question", opportunity.research_question),
            target_weight=updates.get("target_weight", opportunity.target_weight),
            notes=updates.get("notes", opportunity.notes),
            links=links.get(opportunity.id) or OpportunityLinks(),
            source_memo_id=opportunity.source_memo_id,
        )
        if error and not override_reason:
            raise OpportunityValidationError(error)
        if error and override_reason:
            history_note = f"Override from {previous_status}: {override_reason}"
        else:
            history_note = f"Moved from {previous_status}."
    else:
        history_note = None

    for field_name, value in updates.items():
        if field_name == "thesis" and value is None:
            raise OpportunityValidationError("Opportunity thesis is required.")
        setattr(opportunity, field_name, value)

    if proposed_status != previous_status:
        history = list(opportunity.status_history or [])
        history.append(_status_event(str(proposed_status), history_note or ""))
        opportunity.status_history = history
        if "next_action" not in updates:
            opportunity.next_action = _default_next_action(str(proposed_status))

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
            "overridden": bool(override_reason),
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

    links = await _load_links(session, user, [opportunity])
    return _opportunity_response(opportunity, links.get(opportunity.id))


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


def _opportunity_response(
    opportunity: Opportunity,
    links: OpportunityLinks | None = None,
) -> OpportunityResponse:
    source_scores = opportunity.source_memo.scores if opportunity.source_memo else {}
    resolved = links or OpportunityLinks()
    tape = [
        event
        for event in (opportunity.status_history or [])
        if event.get("event") == "radar_tape"
    ][-3:]
    resolved.tape = tape
    resolved.blockers = status_blockers(
        opportunity.status,
        thesis=opportunity.thesis,
        research_question=opportunity.research_question,
        target_weight=opportunity.target_weight,
        notes=opportunity.notes,
        links=resolved,
        source_memo_id=opportunity.source_memo_id,
        for_next=True,
    )
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
        links=resolved,
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
    if status == "discovered":
        return "Screen whether this name deserves Ticker Analyst time."
    if status == "screening":
        return "Open Ticker Analyst and decide whether to research."
    if status == "research":
        return "Save a ticker memo, then promote to candidate."
    if status == "watchlist":
        return "Hold in the queue until a thesis trigger. This is not the radar watchlist."
    if status == "candidate":
        return "Set thesis, research question, and target weight, then run pre-trade risk."
    if status == "approved":
        return "Record the fill in the Trade Journal after a passing pre-trade check."
    if status == "active_position":
        return "Watch the thesis. Close in the journal when the position is done."
    if status == "exited":
        return "Write the close note and move to post-mortem."
    if status == "post_mortem":
        return "Review whether thesis, timing, and sizing were right."
    return "Complete research review and decide whether to promote."


NEXT_STATUS = {
    "discovered": "screening",
    "screening": "research",
    "research": "candidate",
    "watchlist": "candidate",
    "candidate": "approved",
    "approved": "active_position",
    "active_position": "exited",
    "exited": "post_mortem",
}


async def sync_opportunities_for_instrument(
    session: AsyncSession,
    *,
    owner_user_id: str,
    instrument: Instrument,
) -> None:
    """Advance queued names when a live fill or close actually happens."""
    opportunities = list(
        await session.scalars(
            select(Opportunity)
            .options(selectinload(Opportunity.instrument))
            .where(Opportunity.owner_user_id == owner_user_id)
            .where(Opportunity.instrument_id == instrument.id)
            .where(Opportunity.status.notin_(("rejected", "post_mortem")))
        )
    )
    if not opportunities:
        return

    position = await session.scalar(
        select(Position)
        .join(Portfolio, Portfolio.id == Position.portfolio_id)
        .where(Portfolio.owner_user_id == owner_user_id)
        .where(Position.instrument_id == instrument.id)
        .where(Position.quantity > 0)
        .where(Position.closed_at.is_(None))
    )
    now = datetime.now(timezone.utc)
    for opportunity in opportunities:
        if position is not None and opportunity.status != "active_position":
            if opportunity.status in CLOSED_STATUSES:
                continue
            _system_status_move(
                opportunity,
                "active_position",
                "Filled trade recorded.",
                now,
            )
        elif position is None and opportunity.status == "active_position":
            _system_status_move(opportunity, "exited", "Position closed.", now)


def _system_status_move(
    opportunity: Opportunity,
    status: str,
    note: str,
    now: datetime,
) -> None:
    previous = opportunity.status
    opportunity.status = status
    history = list(opportunity.status_history or [])
    history.append(_status_event(status, note))
    opportunity.status_history = history
    opportunity.next_action = _default_next_action(status)
    if status in CLOSED_STATUSES:
        opportunity.closed_at = now
    else:
        opportunity.closed_at = None
    logger.info(
        "opportunity_synced_from_book",
        extra={
            "opportunity_id": str(opportunity.id),
            "ticker": opportunity.instrument.ticker if opportunity.instrument else None,
            "from_status": previous,
            "to_status": status,
        },
    )


def _paginate(
    rows: list,
    page: int,
    page_size: int,
) -> tuple[int, int, int, int, list]:
    safe_size = min(max(page_size, 1), 100)
    total = len(rows)
    total_pages = max(1, (total + safe_size - 1) // safe_size) if total else 1
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * safe_size
    return safe_page, safe_size, total, total_pages, rows[start : start + safe_size]


async def _load_links(
    session: AsyncSession,
    user: AuthenticatedUser,
    opportunities: list[Opportunity],
) -> dict:
    if not opportunities:
        return {}
    instrument_ids = {opportunity.instrument_id for opportunity in opportunities}
    tickers: set[str] = set()
    for opportunity in opportunities:
        ticker = opportunity.instrument.ticker.upper()
        tickers.add(ticker)
        tickers.add(quote_symbol_for(opportunity.instrument))

    memos = list(
        await session.scalars(
            select(TickerMemo)
            .where(TickerMemo.owner_user_id == user.id)
            .where(TickerMemo.instrument_id.in_(instrument_ids))
            .order_by(TickerMemo.memo_date.desc(), TickerMemo.created_at.desc())
        )
    )
    memo_by_instrument: dict = {}
    for memo in memos:
        memo_by_instrument.setdefault(memo.instrument_id, memo)

    snapshots = []
    if tickers:
        snapshots = list(
            await session.scalars(
                select(RadarSnapshot)
                .where(RadarSnapshot.ticker.in_(tickers))
                .distinct(RadarSnapshot.ticker)
                .order_by(RadarSnapshot.ticker, RadarSnapshot.as_of.desc())
            )
        )
    snapshot_by_ticker: dict = {}
    for snapshot in snapshots:
        snapshot_by_ticker.setdefault(snapshot.ticker.upper(), snapshot)

    positions = list(
        await session.scalars(
            select(Position)
            .join(Portfolio, Portfolio.id == Position.portfolio_id)
            .where(Portfolio.owner_user_id == user.id)
            .where(Position.instrument_id.in_(instrument_ids))
            .where(Position.quantity > 0)
            .where(Position.closed_at.is_(None))
        )
    )
    position_by_instrument = {position.instrument_id: position for position in positions}

    trades = list(
        await session.scalars(
            select(Trade)
            .join(Portfolio, Portfolio.id == Trade.portfolio_id)
            .where(Portfolio.owner_user_id == user.id)
            .where(Trade.instrument_id.in_(instrument_ids))
            .order_by(Trade.trade_date.desc())
        )
    )
    trade_by_instrument: dict = {}
    for trade in trades:
        trade_by_instrument.setdefault(trade.instrument_id, trade)

    checks = list(
        await session.scalars(
            select(PreTradeRiskCheck)
            .where(PreTradeRiskCheck.owner_user_id == user.id)
            .order_by(PreTradeRiskCheck.checked_at.desc())
            .limit(200)
        )
    )
    check_by_ticker: dict = {}
    for check in checks:
        payload = check.request_payload or {}
        instrument = payload.get("instrument") or {}
        ticker = str(instrument.get("ticker") or "").upper()
        if ticker and ticker not in check_by_ticker:
            check_by_ticker[ticker] = check

    links: dict = {}
    for opportunity in opportunities:
        ticker = opportunity.instrument.ticker.upper()
        quote_symbol = quote_symbol_for(opportunity.instrument)
        memo = opportunity.source_memo or memo_by_instrument.get(opportunity.instrument_id)
        snapshot = snapshot_by_ticker.get(quote_symbol) or snapshot_by_ticker.get(ticker)
        check = check_by_ticker.get(quote_symbol) or check_by_ticker.get(ticker)
        position = position_by_instrument.get(opportunity.instrument_id)
        trade = trade_by_instrument.get(opportunity.instrument_id)
        evidence = dict(snapshot.evidence or {}) if snapshot else {}
        links[opportunity.id] = OpportunityLinks(
            memo=(
                OpportunityMemoLink(
                    id=memo.id,
                    memo_date=memo.memo_date,
                    classification=memo.classification,
                    executive_view=memo.executive_view,
                )
                if memo is not None
                else None
            ),
            radar=(
                OpportunityRadarLink(
                    ticker=snapshot.ticker,
                    price=snapshot.price,
                    change_pct=snapshot.change_pct,
                    flags=list(snapshot.flags or []),
                    scan_state=str(evidence["scan_state"]) if evidence.get("scan_state") else None,
                    scan_delta_change_pct=(
                        str(evidence["scan_delta_change_pct"])
                        if evidence.get("scan_delta_change_pct") is not None
                        else None
                    ),
                    as_of=snapshot.source_as_of or snapshot.as_of,
                    carried_forward=bool(snapshot.carried_forward),
                )
                if snapshot is not None
                else None
            ),
            pre_trade=(
                OpportunityRiskLink(
                    id=check.id,
                    decision=check.decision,
                    risk_level=check.risk_level,
                    checked_at=check.checked_at,
                )
                if check is not None
                else None
            ),
            position=(
                OpportunityPositionLink(
                    quantity=position.quantity,
                    average_cost=position.average_cost,
                    market_value=position.market_value,
                    unrealized_pnl=position.unrealized_pnl,
                )
                if position is not None
                else None
            ),
            last_trade=(
                OpportunityTradeLink(
                    id=trade.id,
                    side=trade.side,
                    quantity=trade.quantity,
                    executed_price=trade.executed_price,
                    trade_date=trade.trade_date,
                    status=trade.status,
                )
                if trade is not None
                else None
            ),
        )
    return links


def status_gate_error(
    status: str,
    *,
    thesis: str | None,
    research_question: str | None,
    target_weight: object,
    notes: str | None,
    links: OpportunityLinks,
    source_memo_id,
) -> str | None:
    blockers = status_blockers(
        status,
        thesis=thesis,
        research_question=research_question,
        target_weight=target_weight,
        notes=notes,
        links=links,
        source_memo_id=source_memo_id,
        for_next=False,
    )
    return blockers[0] if blockers else None


def status_blockers(
    status_or_current: str,
    *,
    thesis: str | None,
    research_question: str | None,
    target_weight: object,
    notes: str | None,
    links: OpportunityLinks,
    source_memo_id,
    for_next: bool,
) -> list[str]:
    status = NEXT_STATUS.get(status_or_current, status_or_current) if for_next else status_or_current
    blockers: list[str] = []
    has_memo = source_memo_id is not None or links.memo is not None
    if status == "research" and not has_memo:
        blockers.append("Save a Ticker Analyst memo before moving to Research.")
    if status == "candidate":
        if not (thesis or "").strip():
            blockers.append("Candidate requires a thesis.")
        if not (research_question or "").strip():
            blockers.append("Candidate requires a research question.")
        if target_weight is None:
            blockers.append("Candidate requires a target weight.")
    if status == "approved":
        if links.pre_trade is None:
            blockers.append("Run a pre-trade risk check in Risk Centre before Approved.")
        elif links.pre_trade.decision != "approve":
            blockers.append(
                f"Latest pre-trade decision is {links.pre_trade.decision}, not approve."
            )
    if status == "active_position" and links.position is None:
        blockers.append("Record a live fill in the Trade Journal before Active Position.")
    if status == "exited" and links.position is not None:
        blockers.append("Close the live position before Exited.")
    if status == "post_mortem" and not (notes or "").strip():
        blockers.append("Write a close note before Post-Mortem.")
    return blockers


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
