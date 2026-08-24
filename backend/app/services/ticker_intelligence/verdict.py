from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.ticker_intelligence import (
    TickerScoreResponse,
    TickerVerdictContextResponse,
    TickerVerdictResponse,
)
from app.core.auth import AuthenticatedUser
from app.services.market_data.quote_cache import get_cached_quote_price
from app.services.ticker_intelligence.analysis import get_ticker_desk
from app.services.ticker_intelligence.market_data import (
    prefill_ticker,
    resolve_market_hint,
)
from app.services.ticker_intelligence.scoring import TickerScore, score_ticker


async def build_ticker_verdict(
    session: AsyncSession,
    ticker: str,
    *,
    market: str | None = None,
    user: AuthenticatedUser,
) -> TickerVerdictResponse:
    prefill = await prefill_ticker(ticker, market_hint=market, scope="analysis")
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

    top_scores = sorted(scorecard.scores, key=lambda item: item.score, reverse=True)
    low_scores = sorted(scorecard.scores, key=lambda item: item.score)
    warnings = _warnings(prefill.source_warnings, scorecard.confidence_score)

    return TickerVerdictResponse(
        ticker=prefill.instrument.ticker,
        name=prefill.instrument.name,
        market=_market_from_prefill(
            prefill.instrument.ticker,
            prefill.instrument.currency,
            market,
        ),
        generated_at=datetime.now(timezone.utc),
        research_priority=_research_priority(
            scorecard.composite_score,
            scorecard.confidence_score,
            context,
        ),
        initial_view=_initial_view(scorecard.composite_score, scorecard.scores),
        triage_decision=_triage_decision(
            scorecard.composite_score,
            scorecard.confidence_score,
        ),
        action_label=_action_label(scorecard.action, context),
        confidence_score=scorecard.confidence_score,
        conviction_score=scorecard.conviction_score,
        composite_score=scorecard.composite_score,
        recommended_weight=scorecard.recommended_weight,
        top_drivers=[_driver_text(item) for item in top_scores[:3]],
        top_blockers=[_blocker_text(item) for item in low_scores[:3]],
        why_now=_why_now(context),
        next_action=_next_action(
            scorecard.composite_score,
            scorecard.confidence_score,
            context,
        ),
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


def _triage_decision(score: Decimal, confidence: Decimal) -> str:
    if confidence < Decimal("45"):
        return "watch"
    if score >= Decimal("65"):
        return "research"
    if score >= Decimal("45"):
        return "watch"
    return "reject"


def _market_from_prefill(ticker: str, currency: str, market: str | None) -> str:
    if ticker.upper().endswith(".NG") or currency.upper() == "NGN":
        return "NG"
    return resolve_market_hint(market)


def _research_priority(
    score: Decimal,
    confidence: Decimal,
    context: TickerVerdictContextResponse,
) -> str:
    if confidence >= Decimal("65") and score >= Decimal("80"):
        return "high"
    if confidence >= Decimal("50") and score >= Decimal("65"):
        return "medium"
    if context.radar_state or context.latest_news_title or context.has_position:
        return "medium"
    return "low"


def _initial_view(score: Decimal, scores: list[TickerScore]) -> str:
    valuation = next((item.score for item in scores if item.name == "Valuation"), None)
    if score >= Decimal("75"):
        return "attractive"
    if score >= Decimal("62"):
        return "constructive"
    if valuation is not None and valuation < Decimal("40"):
        return "expensive"
    if score >= Decimal("45"):
        return "neutral"
    return "weak"


def _action_label(action: str, context: TickerVerdictContextResponse) -> str:
    if context.has_position:
        return {
            "buy": "Add candidate",
            "hold": "Maintain",
            "watch": "Review",
            "avoid": "Trim / exit review",
        }.get(action, "Review")
    return {
        "buy": "Buy candidate",
        "hold": "Research candidate",
        "watch": "Watch",
        "avoid": "Avoid",
    }.get(action, "Watch")


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
    score: Decimal,
    confidence: Decimal,
    context: TickerVerdictContextResponse,
) -> str:
    decision = _triage_decision(score, confidence)
    if confidence < Decimal("45"):
        return "Keep on watch and improve data coverage before capital work."
    if context.has_position and decision == "reject":
        return "Open Risk Centre and review trim or exit before making changes."
    if decision == "research":
        if context.opportunity_status:
            return "Continue deep research and update the existing opportunity."
        return "Proceed to deep research before moving toward a capital decision."
    if decision == "watch":
        return "Add or keep on watchlist; wait for stronger evidence."
    return "Reject for now; revisit only if thesis or evidence changes."


def _warnings(source_warnings: list[str], confidence: Decimal) -> list[str]:
    warnings = list(dict.fromkeys(source_warnings))
    if confidence < Decimal("45"):
        warnings.insert(0, "Data coverage is too thin for a capital decision.")
    warnings.append("Quick Triage is research screening only, not trade approval.")
    return warnings
