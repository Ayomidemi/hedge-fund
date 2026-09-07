from dataclasses import dataclass, field
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
    capital_score: Decimal | None = None
    timing_score: Decimal | None = None
    capital_coverage: Decimal = Decimal("0.00")
    timing_coverage: Decimal = Decimal("0.00")
    hard_blockers: list[str] = field(default_factory=list)


def score_ticker(metrics: TickerMetricsInput, asset_class: str) -> TickerScorecard:
    quality = _quality_score(metrics)
    growth = _growth_score(metrics)
    valuation = _valuation_score(metrics)
    leverage = _leverage_score(metrics)
    trend = _trend_score(metrics)
    relative = _relative_strength_score(metrics)
    volatility = _volatility_score(metrics)

    capital_parts = [
        ("Quality", quality, Decimal("0.30"), _quality_note(metrics)),
        ("Growth", growth, Decimal("0.25"), _growth_note(metrics)),
        ("Valuation", valuation, Decimal("0.25"), _valuation_note(metrics)),
        ("Balance Sheet Risk", leverage, Decimal("0.20"), _leverage_note(metrics)),
    ]
    timing_parts = [
        ("Trend", trend, Decimal("0.40"), _trend_note(metrics)),
        ("Relative Strength", relative, Decimal("0.35"), _relative_note(metrics)),
        ("Volatility", volatility, Decimal("0.25"), _volatility_note(metrics)),
    ]

    capital_score, capital_coverage = _weighted_optional(
        [(score, weight) for _, score, weight, _ in capital_parts]
    )
    timing_score, timing_coverage = _weighted_optional(
        [(score, weight) for _, score, weight, _ in timing_parts]
    )
    hard_blockers = _hard_capital_blockers(metrics)

    composite = _composite_score(capital_score, timing_score)
    confidence = _confidence_score(
        metrics,
        capital_coverage=capital_coverage,
        timing_coverage=timing_coverage,
    )
    conviction = _quantize(
        (composite * Decimal("0.70")) + (confidence * Decimal("0.30"))
    )
    classification = classify_score(
        composite,
        confidence,
        capital_score=capital_score,
        capital_coverage=capital_coverage,
        hard_blockers=hard_blockers,
    )
    action = action_from_score(
        composite,
        confidence,
        capital_score=capital_score,
        capital_coverage=capital_coverage,
        hard_blockers=hard_blockers,
    )
    recommended_weight = recommended_weight_from_score(
        composite,
        confidence,
        asset_class,
        capital_score=capital_score,
        capital_coverage=capital_coverage,
        hard_blockers=hard_blockers,
    )

    display_scores = _display_scores(capital_parts, timing_parts, timing_score)
    evidence_summary = (
        f"Capital { _fmt_optional(capital_score) }/100 "
        f"({capital_coverage:.0f}% coverage); "
        f"timing { _fmt_optional(timing_score) }/100 "
        f"({timing_coverage:.0f}% coverage); "
        f"{_provided_metric_count(metrics)} of {_metric_count()} metrics supplied."
    )

    return TickerScorecard(
        composite_score=composite,
        confidence_score=confidence,
        conviction_score=conviction,
        classification=classification,
        action=action,
        recommended_weight=recommended_weight,
        scores=display_scores,
        evidence_summary=evidence_summary,
        capital_score=capital_score,
        timing_score=timing_score,
        capital_coverage=_quantize(capital_coverage),
        timing_coverage=_quantize(timing_coverage),
        hard_blockers=hard_blockers,
    )


def classify_score(
    score: Decimal,
    confidence: Decimal,
    *,
    capital_score: Decimal | None = None,
    capital_coverage: Decimal | None = None,
    hard_blockers: list[str] | None = None,
) -> str:
    coverage = capital_coverage if capital_coverage is not None else Decimal("100")
    if hard_blockers:
        return "hard capital pass"
    if confidence < Decimal("45") or coverage < Decimal("40"):
        return "data-incomplete watchlist"
    effective = capital_score if capital_score is not None else score
    if effective >= Decimal("80"):
        return "high-conviction candidate"
    if effective >= Decimal("65"):
        return "research candidate"
    if effective >= Decimal("50"):
        return "watchlist"
    if effective >= Decimal("35"):
        return "low-conviction"
    return "hard capital pass"


def action_from_score(
    score: Decimal,
    confidence: Decimal,
    *,
    capital_score: Decimal | None = None,
    capital_coverage: Decimal | None = None,
    hard_blockers: list[str] | None = None,
) -> str:
    coverage = capital_coverage if capital_coverage is not None else Decimal("100")
    if hard_blockers:
        return "avoid"
    if confidence < Decimal("45") or coverage < Decimal("40"):
        return "watch"
    effective = capital_score if capital_score is not None else score
    if effective >= Decimal("82"):
        return "buy"
    if effective >= Decimal("65"):
        return "hold"
    if effective >= Decimal("45"):
        return "watch"
    return "avoid"


def recommended_weight_from_score(
    score: Decimal,
    confidence: Decimal,
    asset_class: str,
    *,
    capital_score: Decimal | None = None,
    capital_coverage: Decimal | None = None,
    hard_blockers: list[str] | None = None,
) -> Decimal:
    coverage = capital_coverage if capital_coverage is not None else Decimal("100")
    if hard_blockers:
        return Decimal("0.0000")
    if confidence < Decimal("45") or coverage < Decimal("40"):
        return Decimal("0.0000")
    effective = capital_score if capital_score is not None else score
    if effective < Decimal("65"):
        return Decimal("0.0000")

    max_weight = Decimal("0.0500")
    if asset_class in {"etf", "bond", "cash_equivalent"}:
        max_weight = Decimal("0.2000")
    if asset_class == "commodity":
        max_weight = Decimal("0.0750")

    score_fraction = min((effective - Decimal("65")) / Decimal("35"), Decimal("1"))
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
        "capital_score": (
            str(scorecard.capital_score) if scorecard.capital_score is not None else None
        ),
        "timing_score": (
            str(scorecard.timing_score) if scorecard.timing_score is not None else None
        ),
        "capital_coverage": str(scorecard.capital_coverage),
        "timing_coverage": str(scorecard.timing_coverage),
        "hard_blockers": scorecard.hard_blockers,
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


def _display_scores(
    capital_parts: list[tuple[str, Decimal | None, Decimal, str]],
    timing_parts: list[tuple[str, Decimal | None, Decimal, str]],
    timing_score: Decimal | None,
) -> list[TickerScore]:
    scores: list[TickerScore] = []
    for name, score, weight, notes in capital_parts:
        scores.append(
            TickerScore(
                name,
                score if score is not None else Decimal("0"),
                weight,
                notes if score is not None else f"{notes} (missing — excluded).",
            )
        )
    # Keep a single Momentum row for UI compatibility with older scorecards.
    momentum_notes = (
        "Timing blends trend, six-month relative strength, and volatility once."
        if timing_score is not None
        else "Timing score is provisional until trend, relative strength, or volatility is entered."
    )
    scores.append(
        TickerScore(
            "Momentum",
            timing_score if timing_score is not None else Decimal("0"),
            Decimal("0.20"),
            momentum_notes,
        )
    )
    return scores


def _hard_capital_blockers(metrics: TickerMetricsInput) -> list[str]:
    blockers: list[str] = []
    debt = metrics.debt_to_equity
    fcf = metrics.free_cash_flow_yield_pct
    margin = metrics.net_margin_pct

    if debt is not None and debt >= Decimal("6"):
        blockers.append(f"Extreme leverage (D/E {debt}).")
    elif (
        debt is not None
        and debt >= Decimal("4")
        and (
            (fcf is not None and fcf < Decimal("0"))
            or (margin is not None and margin < Decimal("0"))
        )
    ):
        blockers.append(
            f"High leverage (D/E {debt}) with negative cash generation or margin."
        )

    if fcf is not None and fcf <= Decimal("-8") and (
        debt is not None and debt >= Decimal("2")
    ):
        blockers.append(
            f"Severe cash burn (FCF yield {fcf}%) with elevated leverage."
        )

    return blockers


def _quality_score(metrics: TickerMetricsInput) -> Decimal | None:
    return _average_optional(
        [
            _band_score(
                metrics.net_margin_pct,
                [
                    (Decimal("25"), 100),
                    (Decimal("15"), 80),
                    (Decimal("8"), 60),
                    (Decimal("0"), 40),
                ],
            ),
            _band_score(
                metrics.free_cash_flow_yield_pct,
                [
                    (Decimal("6"), 100),
                    (Decimal("3"), 75),
                    (Decimal("0"), 50),
                    (Decimal("-3"), 25),
                ],
            ),
            _inverse_band_score(
                metrics.debt_to_equity,
                [
                    (Decimal("0.4"), 100),
                    (Decimal("1.0"), 75),
                    (Decimal("2.0"), 45),
                    (Decimal("4.0"), 20),
                ],
            ),
        ]
    )


def _growth_score(metrics: TickerMetricsInput) -> Decimal | None:
    return _average_optional(
        [
            _band_score(
                metrics.revenue_growth_pct,
                [
                    (Decimal("20"), 100),
                    (Decimal("10"), 80),
                    (Decimal("3"), 60),
                    (Decimal("0"), 45),
                ],
            ),
            _band_score(
                metrics.earnings_growth_pct,
                [
                    (Decimal("25"), 100),
                    (Decimal("12"), 80),
                    (Decimal("3"), 60),
                    (Decimal("0"), 45),
                ],
            ),
        ]
    )


def _valuation_score(metrics: TickerMetricsInput) -> Decimal | None:
    pe = metrics.forward_pe if metrics.forward_pe is not None else metrics.pe_ratio
    return _average_optional(
        [
            _inverse_band_score(
                pe,
                [
                    (Decimal("12"), 100),
                    (Decimal("20"), 75),
                    (Decimal("30"), 50),
                    (Decimal("45"), 25),
                ],
            ),
            _band_score(
                metrics.free_cash_flow_yield_pct,
                [
                    (Decimal("8"), 100),
                    (Decimal("5"), 80),
                    (Decimal("2"), 60),
                    (Decimal("0"), 40),
                ],
            ),
        ]
    )


def _leverage_score(metrics: TickerMetricsInput) -> Decimal | None:
    return _inverse_band_score(
        metrics.debt_to_equity,
        [
            (Decimal("0.4"), 100),
            (Decimal("1.0"), 75),
            (Decimal("2.0"), 45),
            (Decimal("4.0"), 20),
        ],
    )


def _trend_score(metrics: TickerMetricsInput) -> Decimal | None:
    return _band_score(
        metrics.price_vs_200d_pct,
        [
            (Decimal("20"), 100),
            (Decimal("8"), 80),
            (Decimal("0"), 60),
            (Decimal("-10"), 35),
        ],
    )


def _relative_strength_score(metrics: TickerMetricsInput) -> Decimal | None:
    return _band_score(
        metrics.relative_strength_6m_pct,
        [
            (Decimal("20"), 100),
            (Decimal("8"), 80),
            (Decimal("0"), 60),
            (Decimal("-10"), 35),
        ],
    )


def _volatility_score(metrics: TickerMetricsInput) -> Decimal | None:
    return _inverse_band_score(
        metrics.volatility_30d_pct,
        [
            (Decimal("18"), 100),
            (Decimal("30"), 75),
            (Decimal("50"), 45),
            (Decimal("75"), 20),
        ],
    )


def _composite_score(
    capital_score: Decimal | None,
    timing_score: Decimal | None,
) -> Decimal:
    if capital_score is not None and timing_score is not None:
        return _quantize(
            (capital_score * Decimal("0.65")) + (timing_score * Decimal("0.35"))
        )
    if capital_score is not None:
        return _quantize(capital_score)
    if timing_score is not None:
        return _quantize(timing_score)
    return Decimal("50.00")


def _confidence_score(
    metrics: TickerMetricsInput,
    *,
    capital_coverage: Decimal,
    timing_coverage: Decimal,
) -> Decimal:
    completeness = Decimal(_provided_metric_count(metrics)) / Decimal(_metric_count())
    # Capital coverage dominates confidence for capital decisions.
    coverage_blend = (
        (capital_coverage * Decimal("0.70")) + (timing_coverage * Decimal("0.30"))
    ) / Decimal("100")
    blended = (completeness * Decimal("40")) + (coverage_blend * Decimal("40"))
    return _quantize(Decimal("20") + blended)


def _provided_metric_count(metrics: TickerMetricsInput) -> int:
    return sum(1 for value in metrics.model_dump().values() if value is not None)


def _metric_count() -> int:
    return len(TickerMetricsInput.model_fields)


def _quality_note(metrics: TickerMetricsInput) -> str:
    if metrics.net_margin_pct is None and metrics.free_cash_flow_yield_pct is None:
        return "Quality score excluded until margin or cash-flow data is entered."
    return "Quality reflects margin strength, cash generation, and balance-sheet load."


def _growth_note(metrics: TickerMetricsInput) -> str:
    if metrics.revenue_growth_pct is None and metrics.earnings_growth_pct is None:
        return "Growth score excluded until revenue or earnings growth is entered."
    return "Growth combines revenue and earnings expansion."


def _valuation_note(metrics: TickerMetricsInput) -> str:
    if (
        metrics.pe_ratio is None
        and metrics.forward_pe is None
        and metrics.free_cash_flow_yield_pct is None
    ):
        return "Valuation score excluded until multiple or cash-flow yield data is entered."
    return "Valuation favors lower earnings multiples and stronger cash-flow yield."


def _leverage_note(metrics: TickerMetricsInput) -> str:
    if metrics.debt_to_equity is None:
        return "Leverage score excluded until debt-to-equity is entered."
    return "Balance-sheet risk rewards lower leverage (volatility is timing-only)."


def _trend_note(metrics: TickerMetricsInput) -> str:
    if metrics.price_vs_200d_pct is None:
        return "Trend excluded until price vs 200d is entered."
    return "Trend uses price versus the 200-day average."


def _relative_note(metrics: TickerMetricsInput) -> str:
    if metrics.relative_strength_6m_pct is None:
        return "Relative strength excluded until six-month RS is entered."
    return "Six-month relative strength versus the market."


def _volatility_note(metrics: TickerMetricsInput) -> str:
    if metrics.volatility_30d_pct is None:
        return "Volatility excluded until 30d realized vol is entered."
    return "Volatility is used once in timing (not double-counted in capital)."


def _band_score(
    value: Decimal | None,
    bands: list[tuple[Decimal, int]],
) -> Decimal | None:
    if value is None:
        return None
    for threshold, score in bands:
        if value >= threshold:
            return Decimal(score)
    return Decimal("15")


def _inverse_band_score(
    value: Decimal | None,
    bands: list[tuple[Decimal, int]],
) -> Decimal | None:
    if value is None:
        return None
    for threshold, score in bands:
        if value <= threshold:
            return Decimal(score)
    return Decimal("10")


def _average_optional(values: list[Decimal | None]) -> Decimal | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return _quantize(sum(present, Decimal("0")) / Decimal(len(present)))


def _weighted_optional(
    parts: list[tuple[Decimal | None, Decimal]],
) -> tuple[Decimal | None, Decimal]:
    present = [(score, weight) for score, weight in parts if score is not None]
    if not present:
        return None, Decimal("0")
    weight_sum = sum((weight for _, weight in present), Decimal("0"))
    if weight_sum <= 0:
        return None, Decimal("0")
    score = sum((score * weight for score, weight in present), Decimal("0")) / weight_sum
    # Coverage vs the original weight total for this group.
    full_weight = sum((weight for _, weight in parts), Decimal("0"))
    coverage = (
        (weight_sum / full_weight) * Decimal("100") if full_weight > 0 else Decimal("0")
    )
    return _quantize(score), coverage


def _fmt_optional(value: Decimal | None) -> str:
    return str(value) if value is not None else "n/a"


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
