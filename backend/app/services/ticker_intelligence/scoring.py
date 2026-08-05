from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.api.schemas.ticker_intelligence import TickerMetricsInput


@dataclass(frozen=True)
class TickerScore:
    name: str
    score: Decimal
    weight: Decimal
    notes: str


@dataclass(frozen=True)
class TickerScorecard:
    composite_score: Decimal
    confidence_score: Decimal
    conviction_score: Decimal
    classification: str
    action: str
    recommended_weight: Decimal
    scores: list[TickerScore]
    evidence_summary: str


def score_ticker(metrics: TickerMetricsInput, asset_class: str) -> TickerScorecard:
    scores = [
        TickerScore("Quality", _quality_score(metrics), Decimal("0.25"), _quality_note(metrics)),
        TickerScore("Growth", _growth_score(metrics), Decimal("0.20"), _growth_note(metrics)),
        TickerScore("Valuation", _valuation_score(metrics), Decimal("0.20"), _valuation_note(metrics)),
        TickerScore("Momentum", _momentum_score(metrics), Decimal("0.20"), _momentum_note(metrics)),
        TickerScore("Balance Sheet Risk", _risk_score(metrics), Decimal("0.15"), _risk_note(metrics)),
    ]
    composite = _quantize(
        sum((score.score * score.weight for score in scores), Decimal("0"))
    )
    confidence = _confidence_score(metrics)
    conviction = _quantize((composite * Decimal("0.70")) + (confidence * Decimal("0.30")))
    classification = classify_score(composite, confidence)
    action = action_from_score(composite, confidence)
    recommended_weight = recommended_weight_from_score(composite, confidence, asset_class)
    evidence_summary = (
        f"Composite {composite}/100 with {confidence}/100 confidence from "
        f"{_provided_metric_count(metrics)} of {_metric_count()} supplied metrics."
    )

    return TickerScorecard(
        composite_score=composite,
        confidence_score=confidence,
        conviction_score=conviction,
        classification=classification,
        action=action,
        recommended_weight=recommended_weight,
        scores=scores,
        evidence_summary=evidence_summary,
    )


def classify_score(score: Decimal, confidence: Decimal) -> str:
    if confidence < Decimal("45"):
        return "data-incomplete watchlist"
    if score >= Decimal("80"):
        return "high-conviction candidate"
    if score >= Decimal("65"):
        return "research candidate"
    if score >= Decimal("50"):
        return "watchlist"
    if score >= Decimal("35"):
        return "low-conviction"
    return "avoid"


def action_from_score(score: Decimal, confidence: Decimal) -> str:
    if confidence < Decimal("45"):
        return "watch"
    if score >= Decimal("82"):
        return "buy"
    if score >= Decimal("65"):
        return "hold"
    if score >= Decimal("45"):
        return "watch"
    return "avoid"


def recommended_weight_from_score(
    score: Decimal,
    confidence: Decimal,
    asset_class: str,
) -> Decimal:
    if confidence < Decimal("45") or score < Decimal("65"):
        return Decimal("0.0000")

    max_weight = Decimal("0.0500")
    if asset_class in {"etf", "bond", "cash_equivalent"}:
        max_weight = Decimal("0.2000")
    if asset_class == "commodity":
        max_weight = Decimal("0.0750")

    score_fraction = min((score - Decimal("65")) / Decimal("35"), Decimal("1"))
    confidence_fraction = confidence / Decimal("100")
    return (max_weight * score_fraction * confidence_fraction).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def score_payload(scorecard: TickerScorecard) -> dict[str, str | list[dict[str, str]]]:
    return {
        "composite_score": str(scorecard.composite_score),
        "confidence_score": str(scorecard.confidence_score),
        "conviction_score": str(scorecard.conviction_score),
        "action": scorecard.action,
        "recommended_weight": str(scorecard.recommended_weight),
        "scorecard": [
            {
                "name": score.name,
                "score": str(score.score),
                "weight": str(score.weight),
                "notes": score.notes,
            }
            for score in scorecard.scores
        ],
    }


def _quality_score(metrics: TickerMetricsInput) -> Decimal:
    parts = [
        _band_score(metrics.net_margin_pct, [(Decimal("25"), 100), (Decimal("15"), 80), (Decimal("8"), 60), (Decimal("0"), 40)], 50),
        _band_score(metrics.free_cash_flow_yield_pct, [(Decimal("6"), 100), (Decimal("3"), 75), (Decimal("0"), 50), (Decimal("-3"), 25)], 50),
        _inverse_band_score(metrics.debt_to_equity, [(Decimal("0.4"), 100), (Decimal("1.0"), 75), (Decimal("2.0"), 45), (Decimal("4.0"), 20)], 50),
    ]
    return _average(parts)


def _growth_score(metrics: TickerMetricsInput) -> Decimal:
    return _average(
        [
            _band_score(metrics.revenue_growth_pct, [(Decimal("20"), 100), (Decimal("10"), 80), (Decimal("3"), 60), (Decimal("0"), 45)], 50),
            _band_score(metrics.earnings_growth_pct, [(Decimal("25"), 100), (Decimal("12"), 80), (Decimal("3"), 60), (Decimal("0"), 45)], 50),
        ]
    )


def _valuation_score(metrics: TickerMetricsInput) -> Decimal:
    pe = metrics.forward_pe if metrics.forward_pe is not None else metrics.pe_ratio
    pe_score = _inverse_band_score(
        pe,
        [(Decimal("12"), 100), (Decimal("20"), 75), (Decimal("30"), 50), (Decimal("45"), 25)],
        50,
    )
    fcf_score = _band_score(
        metrics.free_cash_flow_yield_pct,
        [(Decimal("8"), 100), (Decimal("5"), 80), (Decimal("2"), 60), (Decimal("0"), 40)],
        50,
    )
    return _average([pe_score, fcf_score])


def _momentum_score(metrics: TickerMetricsInput) -> Decimal:
    trend_score = _band_score(
        metrics.price_vs_200d_pct,
        [(Decimal("20"), 100), (Decimal("8"), 80), (Decimal("0"), 60), (Decimal("-10"), 35)],
        50,
    )
    relative_score = _band_score(
        metrics.relative_strength_6m_pct,
        [(Decimal("20"), 100), (Decimal("8"), 80), (Decimal("0"), 60), (Decimal("-10"), 35)],
        50,
    )
    volatility_score = _inverse_band_score(
        metrics.volatility_30d_pct,
        [(Decimal("20"), 90), (Decimal("35"), 70), (Decimal("55"), 40), (Decimal("80"), 20)],
        50,
    )
    return _average([trend_score, relative_score, volatility_score])


def _risk_score(metrics: TickerMetricsInput) -> Decimal:
    debt_score = _inverse_band_score(
        metrics.debt_to_equity,
        [(Decimal("0.4"), 100), (Decimal("1.0"), 75), (Decimal("2.0"), 45), (Decimal("4.0"), 20)],
        50,
    )
    volatility_score = _inverse_band_score(
        metrics.volatility_30d_pct,
        [(Decimal("18"), 100), (Decimal("30"), 75), (Decimal("50"), 45), (Decimal("75"), 20)],
        50,
    )
    return _average([debt_score, volatility_score])


def _confidence_score(metrics: TickerMetricsInput) -> Decimal:
    completeness = Decimal(_provided_metric_count(metrics)) / Decimal(_metric_count())
    return _quantize(Decimal("25") + (completeness * Decimal("75")))


def _provided_metric_count(metrics: TickerMetricsInput) -> int:
    return sum(1 for value in metrics.model_dump().values() if value is not None)


def _metric_count() -> int:
    return len(TickerMetricsInput.model_fields)


def _quality_note(metrics: TickerMetricsInput) -> str:
    if metrics.net_margin_pct is None and metrics.free_cash_flow_yield_pct is None:
        return "Quality score is provisional until margin or cash-flow data is entered."
    return "Quality reflects margin strength, cash generation, and balance-sheet load."


def _growth_note(metrics: TickerMetricsInput) -> str:
    if metrics.revenue_growth_pct is None and metrics.earnings_growth_pct is None:
        return "Growth score is provisional until revenue or earnings growth is entered."
    return "Growth combines revenue and earnings expansion."


def _valuation_note(metrics: TickerMetricsInput) -> str:
    if metrics.pe_ratio is None and metrics.forward_pe is None and metrics.free_cash_flow_yield_pct is None:
        return "Valuation score is provisional until multiple or cash-flow yield data is entered."
    return "Valuation favors lower earnings multiples and stronger cash-flow yield."


def _momentum_note(metrics: TickerMetricsInput) -> str:
    if metrics.price_vs_200d_pct is None and metrics.relative_strength_6m_pct is None:
        return "Momentum score is provisional until trend or relative-strength data is entered."
    return "Momentum reflects trend, six-month relative strength, and volatility drag."


def _risk_note(metrics: TickerMetricsInput) -> str:
    if metrics.debt_to_equity is None and metrics.volatility_30d_pct is None:
        return "Risk score is provisional until leverage or volatility data is entered."
    return "Risk score rewards lower leverage and lower recent volatility."


def _band_score(
    value: Decimal | None,
    bands: list[tuple[Decimal, int]],
    default: int,
) -> Decimal:
    if value is None:
        return Decimal(default)
    for threshold, score in bands:
        if value >= threshold:
            return Decimal(score)
    return Decimal("15")


def _inverse_band_score(
    value: Decimal | None,
    bands: list[tuple[Decimal, int]],
    default: int,
) -> Decimal:
    if value is None:
        return Decimal(default)
    for threshold, score in bands:
        if value <= threshold:
            return Decimal(score)
    return Decimal("10")


def _average(values: list[Decimal]) -> Decimal:
    return _quantize(sum(values, Decimal("0")) / Decimal(len(values)))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
