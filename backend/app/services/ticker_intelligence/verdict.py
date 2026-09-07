from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.ticker_intelligence import (
    TickerScoreResponse,
    TickerTriageEntryPlan,
    TickerVerdictContextResponse,
    TickerVerdictResponse,
)
from app.core.auth import AuthenticatedUser
from app.models import Instrument, TickerTriageRun
from app.services.administration.system_log import record_system_log
from app.services.market_data.quote_cache import get_cached_quote_price
from app.services.portfolio.operating_core import upsert_instrument
from app.services.ticker_intelligence.analysis import get_ticker_desk
from app.services.ticker_intelligence.market_data import (
    prefill_ticker,
    resolve_market_hint,
)
from app.services.ticker_intelligence.scoring import TickerScore, TickerScorecard, score_ticker

CHASE_UP_PCT = Decimal("15")
HOSTILE_TIMING = Decimal("35")
WEAK_CAPITAL = Decimal("35")
STRONG_CAPITAL = Decimal("70")
RESEARCH_CAPITAL = Decimal("55")
MIN_CAPITAL_COVERAGE = Decimal("40")


async def build_ticker_verdict(
    session: AsyncSession,
    ticker: str,
    *,
    market: str | None = None,
    user: AuthenticatedUser,
) -> TickerVerdictResponse:
    response, _instrument = await _compose_ticker_verdict(
        session,
        ticker,
        market=market,
        user=user,
        persist_instrument=False,
    )
    return response


async def create_ticker_triage(
    session: AsyncSession,
    ticker: str,
    *,
    market: str | None = None,
    user: AuthenticatedUser,
) -> TickerVerdictResponse:
    response, instrument = await _compose_ticker_verdict(
        session,
        ticker,
        market=market,
        user=user,
        persist_instrument=True,
    )
    if instrument is None:
        raise RuntimeError("Ticker triage could not resolve an instrument.")

    triage = TickerTriageRun(
        owner_user_id=user.id,
        instrument_id=instrument.id,
        generated_at=response.generated_at,
        market=response.market,
        research_priority=response.research_priority,
        initial_view=response.initial_view,
        triage_decision=response.triage_decision,
        action_label=response.action_label,
        confidence_score=response.confidence_score,
        conviction_score=response.conviction_score,
        composite_score=response.composite_score,
        recommended_weight=response.recommended_weight,
        top_drivers=response.top_drivers,
        top_blockers=response.top_blockers,
        why_now=response.why_now,
        next_action=response.next_action,
        warnings=response.warnings,
        source_reference=response.source_reference,
        provider=response.provider,
        data_timestamp=response.data_timestamp,
        metrics=response.metrics.model_dump(mode="json", exclude_none=True),
        context={
            **response.context.model_dump(mode="json"),
            "capital_score": (
                str(response.capital_score) if response.capital_score is not None else None
            ),
            "timing_score": (
                str(response.timing_score) if response.timing_score is not None else None
            ),
            "capital_coverage": str(response.capital_coverage),
            "timing_coverage": str(response.timing_coverage),
            "hard_blockers": response.hard_blockers,
            "setup_status": response.setup_status,
            "capital_blocked": response.capital_blocked,
            "entry_plan": response.entry_plan.model_dump(mode="json"),
        },
        scorecard=[score.model_dump(mode="json") for score in response.scorecard],
    )
    session.add(triage)
    await session.flush()
    triage_id = triage.id
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="research",
        event="ticker_triage_run",
        message=(
            f"{instrument.ticker} quick triage — "
            f"{response.triage_decision} ({response.research_priority})."
        ),
        context={
            "ticker": instrument.ticker,
            "triage_run_id": str(triage.id),
            "market": response.market,
            "triage_decision": response.triage_decision,
            "research_priority": response.research_priority,
            "composite_score": str(response.composite_score),
            "confidence_score": str(response.confidence_score),
            "capital_score": (
                str(response.capital_score) if response.capital_score is not None else None
            ),
            "timing_score": (
                str(response.timing_score) if response.timing_score is not None else None
            ),
            "setup_status": response.setup_status,
            "capital_blocked": response.capital_blocked,
        },
    )
    await session.commit()

    return response.model_copy(update={"triage_run_id": triage_id})


async def _compose_ticker_verdict(
    session: AsyncSession,
    ticker: str,
    *,
    market: str | None,
    user: AuthenticatedUser,
    persist_instrument: bool,
) -> tuple[TickerVerdictResponse, Instrument | None]:
    prefill = await prefill_ticker(ticker, market_hint=market, scope="triage")
    instrument = await upsert_instrument(session, prefill.instrument) if persist_instrument else None
    if instrument is not None:
        await session.flush()

    live_price = await get_cached_quote_price(session, prefill.instrument.ticker)
    if live_price is not None:
        prefill.metrics.current_price = live_price

    scorecard = score_ticker(prefill.metrics, prefill.instrument.asset_class)
    desk = await get_ticker_desk(session, prefill.instrument.ticker, user)
    context = TickerVerdictContextResponse(
        on_watchlist=desk.on_watchlist,
        has_position=desk.position is not None,
        opportunity_status=desk.opportunity.status if desk.opportunity else None,
        opportunity_priority=desk.opportunity.priority if desk.opportunity else None,
        radar_change_pct=desk.radar.change_pct if desk.radar else None,
        radar_state=desk.radar.scan_state if desk.radar else None,
        latest_news_title=desk.news.title if desk.news else None,
        pre_trade_decision=desk.pre_trade.decision if desk.pre_trade else None,
        pre_trade_risk_level=desk.pre_trade.risk_level if desk.pre_trade else None,
        memo_count=len(desk.memos),
    )

    entry_plan = _entry_plan(scorecard, prefill.metrics.current_price, context)
    triage_decision = _triage_decision(scorecard, context, entry_plan)
    capital_blocked = (
        triage_decision in {"hard_pass", "setup_invalid"}
        or bool(scorecard.hard_blockers)
        or entry_plan.status in {"invalid_chase", "hostile_timing"}
    )
    if capital_blocked:
        entry_plan = entry_plan.model_copy(update={"capital_blocked": True})

    top_scores = sorted(
        [item for item in scorecard.scores if item.score > 0],
        key=lambda item: item.score,
        reverse=True,
    )
    low_scores = sorted(
        [item for item in scorecard.scores if item.score > 0],
        key=lambda item: item.score,
    )
    blockers = list(scorecard.hard_blockers)
    blockers.extend(entry_plan.notes)
    blockers.extend(_blocker_text(item) for item in low_scores[:3])
    warnings = _warnings(
        prefill.source_warnings,
        scorecard.confidence_score,
        scorecard.capital_coverage,
        entry_plan,
    )

    weight = (
        Decimal("0.0000")
        if capital_blocked
        else scorecard.recommended_weight
    )

    response = TickerVerdictResponse(
        ticker=prefill.instrument.ticker,
        name=prefill.instrument.name,
        instrument=prefill.instrument,
        metrics=prefill.metrics,
        market=_market_from_prefill(
            prefill.instrument.ticker,
            prefill.instrument.currency,
            market,
        ),
        generated_at=datetime.now(timezone.utc),
        research_priority=_research_priority(scorecard, context, triage_decision),
        initial_view=_initial_view(scorecard),
        triage_decision=triage_decision,
        action_label=_action_label(triage_decision, context),
        confidence_score=scorecard.confidence_score,
        conviction_score=scorecard.conviction_score,
        composite_score=scorecard.composite_score,
        capital_score=scorecard.capital_score,
        timing_score=scorecard.timing_score,
        capital_coverage=scorecard.capital_coverage,
        timing_coverage=scorecard.timing_coverage,
        hard_blockers=scorecard.hard_blockers,
        setup_status=entry_plan.status,
        capital_blocked=capital_blocked,
        entry_plan=entry_plan,
        recommended_weight=weight,
        top_drivers=[_driver_text(item) for item in top_scores[:3]],
        top_blockers=list(dict.fromkeys(blockers))[:6],
        why_now=_why_now(context),
        next_action=_next_action(triage_decision, scorecard, context, entry_plan),
        warnings=warnings,
        source_reference=prefill.source_reference,
        provider=prefill.provider,
        data_timestamp=prefill.data_timestamp,
        context=context,
        scorecard=[
            TickerScoreResponse(
                name=score.name,
                score=score.score,
                weight=score.weight,
                notes=score.notes,
            )
            for score in scorecard.scores
        ],
    )
    return response, instrument


def _triage_decision(
    scorecard: TickerScorecard,
    context: TickerVerdictContextResponse,
    entry_plan: TickerTriageEntryPlan,
) -> str:
    if scorecard.hard_blockers:
        return "hard_pass"
    if entry_plan.status == "invalid_chase":
        return "setup_invalid"

    capital = scorecard.capital_score
    coverage = scorecard.capital_coverage
    timing = scorecard.timing_score
    research_signal = _has_research_signal(context)

    if coverage < MIN_CAPITAL_COVERAGE or capital is None:
        if research_signal:
            return "research"
        return "watch"

    if capital < WEAK_CAPITAL:
        return "hard_pass"

    if timing is not None and timing < HOSTILE_TIMING and research_signal:
        # Dislocation: worth research, not a capital green light.
        return "research"

    if capital >= STRONG_CAPITAL and (
        timing is None or timing >= Decimal("45")
    ):
        return "candidate"

    if capital >= RESEARCH_CAPITAL or research_signal:
        return "research"

    return "watch"


def _entry_plan(
    scorecard: TickerScorecard,
    current_price: Decimal | None,
    context: TickerVerdictContextResponse,
) -> TickerTriageEntryPlan:
    notes: list[str] = []
    radar_change = context.radar_change_pct
    timing = scorecard.timing_score

    if radar_change is not None and radar_change >= CHASE_UP_PCT:
        notes.append(
            f"Chase risk: radar move is already +{radar_change}% — do not buy the spike."
        )
        return TickerTriageEntryPlan(
            status="invalid_chase",
            capital_blocked=True,
            entry_zone=None,
            invalidation=None,
            max_loss_pct_nav=Decimal("0.00"),
            time_stop_sessions=5,
            chase_note=notes[0],
            notes=notes,
        )

    entry_zone = None
    invalidation = None
    if current_price is not None:
        if radar_change is not None and radar_change <= Decimal("-10"):
            entry_high = current_price
            entry_low = (current_price * Decimal("0.92")).quantize(Decimal("0.01"))
            stop = (current_price * Decimal("0.88")).quantize(Decimal("0.01"))
            entry_zone = f"{entry_low} – {entry_high} (near dislocation print)"
            invalidation = f"Break below {stop} (~12% under print) or thesis breaker."
            notes.append(
                "Dislocation setup: only valid near the flagged print, not after a rebound chase."
            )
        else:
            entry_high = current_price
            entry_low = (current_price * Decimal("0.97")).quantize(Decimal("0.01"))
            stop = (current_price * Decimal("0.92")).quantize(Decimal("0.01"))
            entry_zone = f"{entry_low} – {entry_high}"
            invalidation = f"Break below {stop} or thesis breaker."

    if timing is not None and timing < HOSTILE_TIMING:
        notes.append(
            f"Timing is hostile ({timing}/100) — capital blocked until entry rules are explicit."
        )

    status = "suggested"
    if current_price is None:
        status = "incomplete"
        notes.append("No mark available to propose an entry zone.")
    elif timing is not None and timing < HOSTILE_TIMING:
        status = "hostile_timing"

    return TickerTriageEntryPlan(
        status=status,
        capital_blocked=False,
        entry_zone=entry_zone,
        invalidation=invalidation,
        max_loss_pct_nav=Decimal("1.00"),
        time_stop_sessions=10 if radar_change is not None else 15,
        chase_note=(
            f"Invalidate this setup if price rebounds more than {CHASE_UP_PCT}% "
            "from the triage reference without a new underwriting."
        ),
        notes=notes,
    )


def _market_from_prefill(ticker: str, currency: str, market: str | None) -> str:
    if ticker.upper().endswith(".NG") or currency.upper() == "NGN":
        return "NG"
    return resolve_market_hint(market)


def _research_priority(
    scorecard: TickerScorecard,
    context: TickerVerdictContextResponse,
    triage_decision: str,
) -> str:
    if triage_decision == "hard_pass":
        return "low"
    if triage_decision == "setup_invalid":
        return "low"
    capital = scorecard.capital_score
    if (
        capital is not None
        and capital >= Decimal("80")
        and scorecard.confidence_score >= Decimal("65")
        and scorecard.capital_coverage >= Decimal("65")
    ):
        return "high"
    if triage_decision in {"candidate", "research"}:
        return "medium"
    if _has_research_signal(context):
        return "medium"
    return "low"


def _initial_view(scorecard: TickerScorecard) -> str:
    capital = scorecard.capital_score
    valuation = next(
        (item.score for item in scorecard.scores if item.name == "Valuation"),
        None,
    )
    if capital is None or scorecard.capital_coverage < MIN_CAPITAL_COVERAGE:
        return "unknown"
    if capital >= Decimal("75"):
        return "attractive"
    if capital >= Decimal("62"):
        return "constructive"
    if valuation is not None and valuation < Decimal("40") and valuation > 0:
        return "expensive"
    if capital >= Decimal("45"):
        return "neutral"
    return "weak"


def _action_label(decision: str, context: TickerVerdictContextResponse) -> str:
    if context.has_position:
        return {
            "candidate": "Add candidate",
            "research": "Review / research",
            "watch": "Review",
            "setup_invalid": "Do not add / chase",
            "hard_pass": "Trim / exit review",
            # Legacy persisted values
            "reject": "Trim / exit review",
        }.get(decision, "Review")
    return {
        "candidate": "Research candidate",
        "research": "Research",
        "watch": "Watch",
        "setup_invalid": "Do not chase",
        "hard_pass": "Hard pass",
        "reject": "Hard pass",
    }.get(decision, "Watch")


def _driver_text(score: TickerScore) -> str:
    return f"{score.name}: {score.score}/100. {score.notes}"


def _blocker_text(score: TickerScore) -> str:
    return f"{score.name}: {score.score}/100. {score.notes}"


def _why_now(context: TickerVerdictContextResponse) -> str:
    if context.radar_state:
        return f"Market Radar flagged a {context.radar_state.replace('_', ' ')}."
    if context.latest_news_title:
        return f"Latest stored news: {context.latest_news_title}"
    if context.has_position:
        return "Existing position requires an updated research view."
    if context.opportunity_status:
        return f"Existing Opportunity Queue item is {context.opportunity_status}."
    if context.on_watchlist:
        return "Ticker is already on the radar watchlist."
    return "Manual PM research request."


def _next_action(
    decision: str,
    scorecard: TickerScorecard,
    context: TickerVerdictContextResponse,
    entry_plan: TickerTriageEntryPlan,
) -> str:
    if decision == "hard_pass":
        if context.has_position:
            return "Open Risk Centre and review trim or exit before making changes."
        return "Hard pass on capital — revisit only if leverage, cash flow, or thesis evidence changes."
    if decision == "setup_invalid":
        return (
            "Do not chase. Re-underwrite only at a fresh entry zone after the spike cools, "
            "or pass."
        )
    if scorecard.capital_coverage < MIN_CAPITAL_COVERAGE:
        return "Improve capital data coverage before any size decision; deep research if the anomaly matters."
    if decision == "candidate":
        if context.opportunity_status:
            return "Continue deep research with the suggested entry/invalidation plan before approval."
        return (
            "Proceed to deep research with entry zone, stop, and max loss filled before queue approval."
        )
    if decision == "research":
        if entry_plan.status == "hostile_timing":
            return (
                "Research the dislocation; capital stays blocked until an entry plan is explicit "
                "and price is still inside the zone."
            )
        if context.opportunity_status:
            return "Continue deep research and update the existing opportunity."
        return "Deep research before any capital decision; do not buy from triage alone."
    return "Keep on watch; wait for stronger capital evidence or a cleaner setup."


def _warnings(
    source_warnings: list[str],
    confidence: Decimal,
    capital_coverage: Decimal,
    entry_plan: TickerTriageEntryPlan,
) -> list[str]:
    warnings = list(dict.fromkeys(source_warnings))
    warnings.insert(0, "Quick triage is a research screen, not trade approval.")
    if confidence < Decimal("45") or capital_coverage < MIN_CAPITAL_COVERAGE:
        warnings.insert(0, "Capital data coverage is too thin for a size decision.")
    if entry_plan.status == "invalid_chase":
        warnings.insert(0, "Setup invalid: chase risk after a large upside spike.")
    elif entry_plan.status == "hostile_timing":
        warnings.insert(0, "Timing is hostile — treat any interest as research-only.")
    return list(dict.fromkeys(warnings))


def _has_research_signal(context: TickerVerdictContextResponse) -> bool:
    if context.radar_state:
        return True
    if context.latest_news_title:
        return True
    if context.has_position:
        return True
    if context.radar_change_pct is not None and abs(context.radar_change_pct) >= Decimal(
        "5"
    ):
        return True
    return False
