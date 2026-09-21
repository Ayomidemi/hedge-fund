from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.invest import (
    InvestInstrumentResearchResponse,
    InvestPeaseFactorResponse,
    InvestPeaseViewResponse,
    InvestResearchMetricResponse,
    InvestResearchSectionResponse,
)
from app.api.schemas.ticker_intelligence import TickerMetricsInput
from app.models import Instrument, InstrumentQuote, RadarSnapshot
from app.services.market_data.quote_cache import get_or_fetch_quote_price
from app.services.portfolio.operating_core import upsert_instrument
from app.services.ticker_intelligence.market_data import (
    MarketDataUnavailableError,
    prefill_ticker,
)
from app.services.ticker_intelligence.scoring import TickerScorecard, score_ticker

logger = logging.getLogger(__name__)

_FACTOR_MAP = {
    "Quality": ("quality", "Business quality"),
    "Growth": ("growth", "Growth"),
    "Valuation": ("valuation", "Valuation"),
    "Balance Sheet Risk": ("risk", "Balance sheet"),
    "Momentum": ("momentum", "Momentum"),
}


async def build_listed_research(
    session: AsyncSession, instrument: Instrument
) -> InvestInstrumentResearchResponse:
    generated_at = datetime.now(timezone.utc)
    quote = await _quote(session, instrument)
    live_price = await get_or_fetch_quote_price(
        session, instrument.ticker, instrument_id=instrument.id
    )
    radar_note = await _radar_note(session, instrument.ticker)
    pease_view: InvestPeaseViewResponse | None = None
    metrics: TickerMetricsInput | None = None

    try:
        prefill = await prefill_ticker(instrument.ticker, scope="analysis")
        instrument = await upsert_instrument(session, prefill.instrument)
        metrics = prefill.metrics
        if live_price is not None:
            metrics.current_price = live_price
        scorecard = score_ticker(metrics, instrument.asset_class)
        pease_view = pease_view_from_scorecard(
            scorecard,
            radar_note=radar_note,
            source=prefill.provider,
            warnings=list(prefill.source_warnings),
        )
    except (MarketDataUnavailableError, Exception) as exc:
        logger.warning("invest_research_prefill_failed ticker=%s error=%s", instrument.ticker, exc)
        pease_view = None
        metrics = None

    return InvestInstrumentResearchResponse(
        ticker=instrument.ticker,
        name=instrument.name,
        generated_at=generated_at,
        overview=_overview(instrument, pease_view),
        sections=_sections(instrument, quote, live_price, pease_view, metrics),
        pease_view=pease_view,
        withheld_capital_signals=_withheld_capital_signals(),
        news_href=f"/invest/news?ticker={instrument.ticker}",
    )


def pease_view_from_scorecard(
    scorecard: TickerScorecard,
    *,
    radar_note: str | None = None,
    source: str | None = None,
    warnings: list[str] | None = None,
) -> InvestPeaseViewResponse:
    stance, stance_label = retail_stance(scorecard)
    factors = [
        _factor(score) for score in scorecard.scores if score.name in _FACTOR_MAP
    ]
    looks_good = [
        f"{factor.label} looks relatively strong ({_score_text(factor.score)})."
        for factor in factors
        if factor.score is not None and factor.score >= Decimal("70")
    ]
    watch_outs = [_retail_note(blocker) for blocker in scorecard.hard_blockers]
    watch_outs.extend(
        f"{factor.label} is a weak spot ({_score_text(factor.score)})."
        for factor in factors
        if factor.score is not None and factor.score <= Decimal("40")
    )
    coverage = scorecard.capital_coverage
    summary = (
        f"{stance_label}. {coverage:.0f}% of the fundamental inputs are filled. "
        "This is a factor snapshot, not a recommendation to buy or sell."
    )
    return InvestPeaseViewResponse(
        stance=stance,
        stance_label=stance_label,
        summary=summary,
        coverage_pct=coverage,
        looks_good=looks_good,
        watch_outs=watch_outs,
        factors=factors,
        radar_note=radar_note,
        source=source,
        warnings=[_retail_note(item) for item in (warnings or [])],
    )


def retail_stance(scorecard: TickerScorecard) -> tuple[str, str]:
    if scorecard.hard_blockers:
        return "caution", "Caution"
    if (
        scorecard.capital_coverage < Decimal("40")
        or scorecard.confidence_score < Decimal("45")
    ):
        return "incomplete", "Not enough data"
    capital = (
        scorecard.capital_score
        if scorecard.capital_score is not None
        else scorecard.composite_score
    )
    if capital >= Decimal("65"):
        return "constructive", "Looks constructive"
    if capital >= Decimal("50"):
        return "mixed", "Mixed"
    return "caution", "Caution"


def ratio_metrics(metrics: TickerMetricsInput) -> list[InvestResearchMetricResponse]:
    return [
        _signed_metric(
            "Revenue growth", _pct(metrics.revenue_growth_pct), metrics.revenue_growth_pct
        ),
        _signed_metric(
            "Earnings growth",
            _pct(metrics.earnings_growth_pct),
            metrics.earnings_growth_pct,
        ),
        _signed_metric("Net margin", _pct(metrics.net_margin_pct), metrics.net_margin_pct),
        _signed_metric(
            "FCF yield",
            _pct(metrics.free_cash_flow_yield_pct),
            metrics.free_cash_flow_yield_pct,
        ),
        InvestResearchMetricResponse(label="P/E", value=_number(metrics.pe_ratio)),
        InvestResearchMetricResponse(
            label="Debt / equity",
            value=_number(metrics.debt_to_equity),
            tone=(
                "negative"
                if metrics.debt_to_equity is not None
                and metrics.debt_to_equity >= Decimal("2")
                else "neutral"
            ),
        ),
        _signed_metric(
            "Vs 200-day", _pct(metrics.price_vs_200d_pct), metrics.price_vs_200d_pct
        ),
        _signed_metric(
            "6m relative strength",
            _pct(metrics.relative_strength_6m_pct),
            metrics.relative_strength_6m_pct,
        ),
        InvestResearchMetricResponse(
            label="30d volatility",
            value=_pct(metrics.volatility_30d_pct),
        ),
    ]


def _sections(
    instrument: Instrument,
    quote: InstrumentQuote | None,
    price: Decimal | None,
    view: InvestPeaseViewResponse | None,
    metrics: TickerMetricsInput | None,
) -> list[InvestResearchSectionResponse]:
    sections = [
        InvestResearchSectionResponse(
            id="instrument_profile",
            title="Instrument profile",
            summary="Identity and listing details from the shared instrument registry.",
            metrics=[
                InvestResearchMetricResponse(
                    label="Asset class",
                    value=instrument.asset_class.replace("_", " ").title(),
                ),
                InvestResearchMetricResponse(
                    label="Exchange",
                    value=instrument.exchange or "Unlisted registry item",
                ),
                InvestResearchMetricResponse(label="Currency", value=instrument.currency),
                InvestResearchMetricResponse(
                    label="Sector",
                    value=instrument.sector or "Not classified",
                ),
            ],
            notes=[
                "Unusual listed-name tape lives on Discover. Bills and bonds stay on Markets.",
                "This is research context, not a Pease Capital recommendation.",
            ],
        ),
        InvestResearchSectionResponse(
            id="price_context",
            title="Price context",
            summary="Latest quote state available to the paper order ticket.",
            metrics=[
                InvestResearchMetricResponse(
                    label="Last price",
                    value=_money(price, instrument.currency),
                ),
                InvestResearchMetricResponse(
                    label="Daily move",
                    value=_pct(quote.change_pct if quote is not None else None),
                    tone=_change_tone(
                        quote.change_pct if quote is not None else None
                    ),
                ),
                InvestResearchMetricResponse(
                    label="Quote source",
                    value=quote.source if quote is not None else "Unavailable",
                ),
                InvestResearchMetricResponse(
                    label="Quote status",
                    value=_quote_status(quote),
                    tone=(
                        "negative"
                        if quote is not None and quote.is_stale
                        else "neutral"
                    ),
                ),
            ],
            notes=[
                "A missing price blocks notional paper orders until quote data is available.",
            ],
        ),
    ]
    if view is None:
        sections.append(
            InvestResearchSectionResponse(
                id="pease_view",
                title="Pease View",
                summary="Live factor scores could not be built for this name yet.",
                notes=[
                    "Price and registry data are still available for the paper ticket.",
                    "Try again shortly if market data is catching up.",
                ],
            )
        )
        return sections

    sections.append(
        InvestResearchSectionResponse(
            id="pease_view",
            title="Pease View",
            summary=view.summary,
            metrics=[
                InvestResearchMetricResponse(
                    label=factor.label,
                    value=_score_text(factor.score),
                    tone=factor.tone,
                )
                for factor in view.factors
            ],
            notes=[*view.looks_good, *view.watch_outs],
        )
    )
    if metrics is not None:
        sections.append(
            InvestResearchSectionResponse(
                id="financials",
                title="Financials",
                summary="Inputs that fed the Pease View. Gaps show as unavailable.",
                metrics=ratio_metrics(metrics),
            )
        )
    if view.radar_note:
        sections.append(
            InvestResearchSectionResponse(
                id="radar_context",
                title="Market tape",
                summary="Simplified unusual-activity note from the shared scanner.",
                notes=[view.radar_note],
            )
        )
    return sections


def _factor(score) -> InvestPeaseFactorResponse:
    factor_id, label = _FACTOR_MAP[score.name]
    missing = "missing" in score.notes.lower() or "excluded" in score.notes.lower()
    value = None if missing else score.score
    return InvestPeaseFactorResponse(
        id=factor_id,
        label=label,
        score=value,
        notes=_retail_note(score.notes),
        tone=_score_tone(value),
    )


def _overview(instrument: Instrument, view: InvestPeaseViewResponse | None) -> str:
    if view is None:
        return (
            f"{instrument.ticker} is available as a listed paper-trading instrument. "
            "Live factor scores could not be built yet; price and identity still apply."
        )
    return (
        f"{instrument.name} ({instrument.ticker}) — {view.stance_label}. "
        f"{view.coverage_pct:.0f}% of the fundamental inputs are filled. "
        "This is a shared factor snapshot, not advice to trade."
    )


async def _quote(session: AsyncSession, instrument: Instrument) -> InstrumentQuote | None:
    return await session.scalar(
        select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument.id)
    )


async def _radar_note(session: AsyncSession, ticker: str) -> str | None:
    row = await session.scalar(
        select(RadarSnapshot)
        .where(RadarSnapshot.ticker == ticker.upper())
        .order_by(RadarSnapshot.as_of.desc())
        .limit(1)
    )
    if row is None or not row.flags:
        return None
    move = _pct(row.change_pct)
    volume = (
        f"{row.volume_ratio:.1f}× volume" if row.volume_ratio is not None else None
    )
    bits = [bit for bit in [move, volume] if bit and bit != "Unavailable"]
    detail = " on ".join(bits) if bits else "an unusual print"
    return (
        f"{row.ticker} is moving differently from its recent pattern ({detail}). "
        "See Discover for the broader tape."
    )


def _signed_metric(
    label: str, value: str, numeric: Decimal | None
) -> InvestResearchMetricResponse:
    return InvestResearchMetricResponse(
        label=label,
        value=value,
        tone=_change_tone(numeric) if numeric is not None else "neutral",
    )


def _score_tone(score: Decimal | None) -> str:
    if score is None:
        return "neutral"
    if score >= Decimal("70"):
        return "positive"
    if score <= Decimal("40"):
        return "negative"
    return "neutral"


def _score_text(score: Decimal | None) -> str:
    if score is None:
        return "Unavailable"
    return f"{score.quantize(Decimal('1'))}/100"


def _pct(value: Decimal | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{value.quantize(Decimal('0.01'))}%"


def _number(value: Decimal | None) -> str:
    if value is None:
        return "Unavailable"
    return str(value.quantize(Decimal("0.01")))


def _money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "Unavailable"
    return f"{currency} {value.quantize(Decimal('0.01'))}"


def _change_tone(value: Decimal | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _quote_status(quote: InstrumentQuote | None) -> str:
    if quote is None:
        return "Unavailable"
    if quote.is_stale:
        return "Stale"
    return "Live"


def _retail_note(text: str) -> str:
    return (
        text.replace("entered", "available")
        .replace(" (missing — excluded).", " (not enough data).")
    )


def _withheld_capital_signals() -> list[str]:
    return [
        "Capital target weights",
        "Expected alpha and model rank",
        "Strategy pod assignment",
        "PM approval state",
        "Portfolio hedge recommendation",
        "Fund-level risk budget",
    ]
