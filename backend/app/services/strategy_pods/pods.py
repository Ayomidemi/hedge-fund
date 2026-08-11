import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.api.schemas.risk_centre import RiskCentreOverviewResponse
from app.api.schemas.strategy_pods import (
    StrategyPodLatestSnapshotResponse,
    StrategyPodOverviewResponse,
    StrategyPodResponse,
    StrategyPodSignalResponse,
    StrategyPodSnapshotResponse,
    StrategyPodUpdate,
)
from app.api.schemas.ticker_intelligence import (
    ModelComparisonRowResponse,
    RegimeModelResponse,
    TickerMemoSummaryResponse,
)
from app.models import MarketPriceBar, StrategyPod, StrategyPodSnapshot
from app.services.risk.risk_centre import build_risk_centre_overview
from app.services.ticker_intelligence.analysis import list_recent_ticker_memos
from app.services.ticker_intelligence.ml_training import (
    MLTrainingDataUnavailableError,
    get_latest_market_regime_model,
    list_predictive_model_comparison,
)

logger = logging.getLogger(__name__)

POD_LIFECYCLE_ORDER = [
    "research",
    "candidate",
    "paper_trading",
    "probationary_capital",
    "core_strategy",
    "reduced_allocation",
    "suspended",
    "retired",
]

POD_STATUS_ORDER = [
    "active",
    "watch",
    "research",
    "sandbox",
    "suspended",
    "retired",
]

DEFAULT_STRATEGY_POD_DEFINITIONS = [
    {
        "code": "macro_regime",
        "name": "Macro Regime Pod",
        "mandate": "Classify the market regime and set the strategic risk posture across asset classes.",
        "status": "active",
        "lifecycle_stage": "paper_trading",
        "capital_allocation_pct": Decimal("20.0000"),
        "risk_budget_pct": Decimal("18.0000"),
        "volatility_target_pct": Decimal("12.0000"),
        "max_drawdown_pct": Decimal("10.0000"),
        "turnover_ceiling_pct": Decimal("50.0000"),
        "approved_instruments": [
            "broad-market ETFs",
            "Treasury ETFs",
            "gold ETFs",
            "cash equivalents",
        ],
        "current_signals": {
            "primary_model": "HMM market regime model",
            "required_inputs": [
                "market breadth",
                "volatility",
                "rates",
                "credit",
                "commodities",
            ],
        },
        "evaluation": {
            "primary_question": "Which regime are we in, and should portfolio risk expand or contract?",
            "minimum_evidence": [
                "regime probability",
                "transition risk",
                "risk-center agreement",
            ],
        },
        "shutdown_criteria": "Suspend overlay if regime state is unstable, confidence collapses, or risk centre enters halt.",
        "notes": "Phase-one version uses price and volatility until macro datasets are connected.",
    },
    {
        "code": "cross_asset_trend",
        "name": "Cross-Asset Trend Pod",
        "mandate": "Identify persistent directional trends across equities, bonds, gold, commodities, and cash proxies.",
        "status": "watch",
        "lifecycle_stage": "research",
        "capital_allocation_pct": Decimal("15.0000"),
        "risk_budget_pct": Decimal("15.0000"),
        "volatility_target_pct": Decimal("14.0000"),
        "max_drawdown_pct": Decimal("10.0000"),
        "turnover_ceiling_pct": Decimal("80.0000"),
        "approved_instruments": [
            "SPY",
            "QQQ",
            "IWM",
            "TLT",
            "IEF",
            "SHY",
            "GLD",
            "DBC",
        ],
        "current_signals": {
            "primary_model": "multi-horizon trend strength",
            "required_inputs": [
                "moving averages",
                "breakouts",
                "realized volatility",
                "asset-class momentum",
            ],
        },
        "evaluation": {
            "primary_question": "Which assets have persistent risk-adjusted direction?",
            "minimum_evidence": [
                "multi-horizon agreement",
                "transaction-cost-aware backtest",
            ],
        },
        "shutdown_criteria": "Suspend if trend turnover overwhelms expected edge or correlations spike.",
        "notes": "Ready to consume the existing price history store before a dedicated trend model is added.",
    },
    {
        "code": "quant_equity",
        "name": "Quantitative Equity Pod",
        "mandate": "Rank equities by systematic factors and predictive relative-return models.",
        "status": "active",
        "lifecycle_stage": "paper_trading",
        "capital_allocation_pct": Decimal("25.0000"),
        "risk_budget_pct": Decimal("25.0000"),
        "volatility_target_pct": Decimal("16.0000"),
        "max_drawdown_pct": Decimal("12.0000"),
        "turnover_ceiling_pct": Decimal("100.0000"),
        "approved_instruments": [
            "US-listed equities",
            "sector ETFs",
            "broad-market ETFs",
        ],
        "current_signals": {
            "primary_model": "ridge/logistic relative-return model",
            "required_inputs": [
                "price features",
                "forward labels",
                "benchmark-relative outcomes",
            ],
        },
        "evaluation": {
            "primary_question": "Which securities are most likely to outperform comparable securities?",
            "minimum_evidence": [
                "validation rows",
                "directional accuracy",
                "simple-model baseline comparison",
            ],
        },
        "shutdown_criteria": "Disable if validation accuracy decays or residual downside becomes unacceptable.",
        "notes": "This is the current home of the predictive ticker model.",
    },
    {
        "code": "fundamental_equity",
        "name": "Fundamental Equity Pod",
        "mandate": "Maintain deep company research, thesis quality, scenario ranges, and watchlist discipline.",
        "status": "active",
        "lifecycle_stage": "candidate",
        "capital_allocation_pct": Decimal("30.0000"),
        "risk_budget_pct": Decimal("25.0000"),
        "volatility_target_pct": Decimal("18.0000"),
        "max_drawdown_pct": Decimal("15.0000"),
        "turnover_ceiling_pct": Decimal("35.0000"),
        "approved_instruments": ["US-listed equities", "liquid ETFs"],
        "current_signals": {
            "primary_model": "AI-assisted ticker analyst memo",
            "required_inputs": [
                "thesis",
                "bull/base/bear cases",
                "risk notes",
                "valuation context",
            ],
        },
        "evaluation": {
            "primary_question": "Does the business quality and valuation justify research time or capital?",
            "minimum_evidence": ["complete memo", "thesis breakers", "portfolio fit"],
        },
        "shutdown_criteria": "Stop adding names if thesis quality weakens or downside cases are not explicit.",
        "notes": "The ticker analyst feeds this pod directly.",
    },
    {
        "code": "relative_value",
        "name": "Relative-Value Pod",
        "mandate": "Research mispricing between economically related instruments without relying only on market direction.",
        "status": "research",
        "lifecycle_stage": "research",
        "capital_allocation_pct": Decimal("0.0000"),
        "risk_budget_pct": Decimal("5.0000"),
        "volatility_target_pct": Decimal("10.0000"),
        "max_drawdown_pct": Decimal("6.0000"),
        "turnover_ceiling_pct": Decimal("120.0000"),
        "approved_instruments": [
            "pairs",
            "sector-relative baskets",
            "ETF relationships",
        ],
        "current_signals": {
            "primary_model": "correlation and spread diagnostics",
            "required_inputs": [
                "correlation",
                "cointegration",
                "borrow/shorting constraints",
                "transaction costs",
            ],
        },
        "evaluation": {
            "primary_question": "Is there a stable relative mispricing after costs and constraints?",
            "minimum_evidence": [
                "spread stability",
                "cost-aware backtest",
                "execution feasibility",
            ],
        },
        "shutdown_criteria": "No live allocation while leverage, shorting, or execution constraints are unresolved.",
        "notes": "Kept research-only during phase one.",
    },
    {
        "code": "experimental_research",
        "name": "Experimental Research Pod",
        "mandate": "Test unconventional models and data sources before they earn a place in a core pod.",
        "status": "sandbox",
        "lifecycle_stage": "research",
        "capital_allocation_pct": Decimal("0.0000"),
        "risk_budget_pct": Decimal("2.0000"),
        "volatility_target_pct": None,
        "max_drawdown_pct": Decimal("4.0000"),
        "turnover_ceiling_pct": Decimal("150.0000"),
        "approved_instruments": ["research-only datasets", "paper-trading candidates"],
        "current_signals": {
            "primary_model": "sandbox experiments",
            "required_inputs": [
                "hypothesis",
                "data provenance",
                "baseline comparison",
                "failure criteria",
            ],
        },
        "evaluation": {
            "primary_question": "Is this idea robust enough to graduate into a production pod?",
            "minimum_evidence": [
                "clear baseline improvement",
                "robustness checks",
                "risk review",
            ],
        },
        "shutdown_criteria": "No live allocation until validation standards are met.",
        "notes": "This protects the core portfolio from exciting but unproven ideas.",
    },
]


@dataclass(frozen=True)
class MarketPriceCoverage:
    bar_count: int
    instrument_count: int
    latest_bar_date: date | None


@dataclass(frozen=True)
class StrategyPodRuntimeContext:
    generated_at: datetime
    risk_overview: RiskCentreOverviewResponse
    latest_regime: RegimeModelResponse | None
    model_comparison: list[ModelComparisonRowResponse]
    recent_memos: list[TickerMemoSummaryResponse]
    price_coverage: MarketPriceCoverage
    warnings: list[str]


@dataclass(frozen=True)
class StrategyPodAssessment:
    live_signals: list[StrategyPodSignalResponse]
    current_signal_score: Decimal | None
    model_confidence: Decimal | None
    allocation_recommendation: str
    evaluation_overlay: dict[str, Any]


async def list_strategy_pods(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> StrategyPodOverviewResponse:
    pods = await _get_or_seed_strategy_pods(session, user)
    latest_snapshots = await _load_latest_snapshots(session, pods)
    context = await _load_runtime_context(session, user)
    responses = [
        _pod_response(pod, context, latest_snapshots.get(pod.id)) for pod in pods
    ]
    allocation_total = _decimal4(
        sum((pod.capital_allocation_pct for pod in pods), Decimal("0"))
    )
    risk_budget_total = _decimal4(
        sum((pod.risk_budget_pct for pod in pods), Decimal("0"))
    )
    unallocated = _decimal4(max(Decimal("0"), Decimal("100") - allocation_total))
    warnings: list[str] = []
    if allocation_total > Decimal("100"):
        warnings.append("Total pod allocation is above 100%; CIO review required.")

    logger.info(
        "strategy_pods_loaded",
        extra={
            "pod_count": len(pods),
            "owner_user_id": user.id,
            "allocation_total_pct": str(allocation_total),
            "risk_level": context.risk_overview.snapshot.risk_level,
        },
    )

    return StrategyPodOverviewResponse(
        generated_at=context.generated_at,
        portfolio_name=context.risk_overview.snapshot.portfolio_name,
        nav=context.risk_overview.snapshot.nav,
        risk_level=context.risk_overview.snapshot.risk_level,
        allocation_total_pct=allocation_total,
        risk_budget_total_pct=risk_budget_total,
        unallocated_pct=unallocated,
        pods=responses,
        warnings=warnings,
    )


async def get_strategy_pod(
    session: AsyncSession,
    code: str,
    user: AuthenticatedUser,
) -> StrategyPodResponse | None:
    pods = await _get_or_seed_strategy_pods(session, user)
    pod = next(
        (item for item in pods if item.code == normalize_strategy_pod_code(code)), None
    )
    if pod is None:
        return None
    latest_snapshots = await _load_latest_snapshots(session, [pod])
    context = await _load_runtime_context(session, user)
    return _pod_response(pod, context, latest_snapshots.get(pod.id))


async def update_strategy_pod(
    session: AsyncSession,
    code: str,
    payload: StrategyPodUpdate,
    user: AuthenticatedUser,
) -> StrategyPodResponse | None:
    pods = await _get_or_seed_strategy_pods(session, user)
    pod = next(
        (item for item in pods if item.code == normalize_strategy_pod_code(code)), None
    )
    if pod is None:
        return None

    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        if field_name == "approved_instruments" and value is not None:
            value = [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, Decimal):
            value = _decimal4(value)
        setattr(pod, field_name, value)

    await session.commit()
    await session.refresh(pod)

    logger.info(
        "strategy_pod_updated",
        extra={
            "pod_code": pod.code,
            "owner_user_id": user.id,
            "status": pod.status,
            "lifecycle_stage": pod.lifecycle_stage,
            "capital_allocation_pct": str(pod.capital_allocation_pct),
        },
    )

    return await get_strategy_pod(session, pod.code, user)


async def capture_strategy_pod_snapshot(
    session: AsyncSession,
    code: str,
    user: AuthenticatedUser,
) -> StrategyPodSnapshotResponse | None:
    pods = await _get_or_seed_strategy_pods(session, user)
    pod = next(
        (item for item in pods if item.code == normalize_strategy_pod_code(code)), None
    )
    if pod is None:
        return None

    context = await _load_runtime_context(session, user)
    response = _pod_response(pod, context, None)
    snapshot = StrategyPodSnapshot(
        strategy_pod_id=pod.id,
        captured_at=context.generated_at,
        as_of_date=context.generated_at.date(),
        status=pod.status,
        lifecycle_stage=pod.lifecycle_stage,
        capital_allocation_pct=pod.capital_allocation_pct,
        risk_budget_pct=pod.risk_budget_pct,
        current_signal_score=response.current_signal_score,
        model_confidence=response.model_confidence,
        risk_level=response.risk_level,
        allocation_recommendation=response.allocation_recommendation,
        payload=_json_payload(response.model_dump(mode="json")),
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)

    logger.info(
        "strategy_pod_snapshot_captured",
        extra={
            "pod_code": pod.code,
            "owner_user_id": user.id,
            "snapshot_id": str(snapshot.id),
            "risk_level": snapshot.risk_level,
            "signal_score": str(snapshot.current_signal_score),
        },
    )

    return _snapshot_to_response(snapshot, pod)


async def list_strategy_pod_snapshots(
    session: AsyncSession,
    code: str,
    user: AuthenticatedUser,
    *,
    limit: int = 20,
) -> list[StrategyPodSnapshotResponse] | None:
    pods = await _get_or_seed_strategy_pods(session, user)
    pod = next(
        (item for item in pods if item.code == normalize_strategy_pod_code(code)), None
    )
    if pod is None:
        return None

    snapshots = await session.scalars(
        select(StrategyPodSnapshot)
        .where(StrategyPodSnapshot.strategy_pod_id == pod.id)
        .order_by(StrategyPodSnapshot.captured_at.desc())
        .limit(limit)
    )
    return [_snapshot_to_response(snapshot, pod) for snapshot in snapshots]


def normalize_strategy_pod_code(code: str) -> str:
    return code.strip().lower().replace("-", "_")


def strategy_pod_allocation_recommendation(
    *,
    code: str,
    status: str,
    lifecycle_stage: str,
    risk_level: str,
    capital_allocation_pct: Decimal,
    current_regime: str | None = None,
    current_signal_score: Decimal | None = None,
    model_confidence: Decimal | None = None,
) -> str:
    normalized_status = status.lower()
    normalized_stage = lifecycle_stage.lower()
    normalized_risk = risk_level.lower()
    normalized_regime = (current_regime or "").lower()
    normalized_code = normalize_strategy_pod_code(code)

    if (
        normalized_status not in POD_STATUS_ORDER
        or normalized_stage not in POD_LIFECYCLE_ORDER
    ):
        return "Governance review required; pod status or lifecycle stage is outside the approved vocabulary."
    if normalized_status in {"suspended", "retired"} or normalized_stage in {
        "suspended",
        "retired",
    }:
        return "No new capital; pod is suspended or retired."
    if normalized_risk == "halt":
        return "No new capital; portfolio-wide trading halt overrides the pod."
    if normalized_risk == "suspend":
        return "Suspend new deployment until central risk clears the portfolio."
    if normalized_risk == "reduce" and capital_allocation_pct > 0:
        return "Reduce new deployment until central risk warnings are resolved."
    if normalized_stage == "research" or normalized_status in {"research", "sandbox"}:
        return "Research-only; collect evidence before live allocation."

    confidence = model_confidence or Decimal("0")
    score = current_signal_score or Decimal("0")
    if normalized_code == "macro_regime" and normalized_regime in {"stress", "shock"}:
        return "Defensive overlay only; reduce gross exposure and keep cash available."
    if normalized_code == "macro_regime" and normalized_regime == "fragile":
        return "Keep allocation below target until trend and risk evidence confirm."
    if confidence >= Decimal("60") and score >= Decimal("60"):
        return "Eligible for limited deployment after pre-trade risk checks."
    if confidence >= Decimal("45") or score >= Decimal("45"):
        return "Paper trade or small watch allocation; evidence is not strong enough for expansion."
    return "Hold allocation steady; signal quality is still weak."


async def _get_or_seed_strategy_pods(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> list[StrategyPod]:
    result = await session.scalars(
        select(StrategyPod).where(StrategyPod.owner_user_id == user.id)
    )
    existing = {pod.code: pod for pod in result}
    created = False
    for definition in DEFAULT_STRATEGY_POD_DEFINITIONS:
        if definition["code"] in existing:
            continue
        pod = StrategyPod(owner_user_id=user.id, **definition)
        session.add(pod)
        existing[pod.code] = pod
        created = True

    if created:
        await session.commit()
        logger.info(
            "strategy_pods_seeded",
            extra={
                "owner_user_id": user.id,
                "pod_count": len(DEFAULT_STRATEGY_POD_DEFINITIONS),
            },
        )

    order = {
        definition["code"]: index
        for index, definition in enumerate(DEFAULT_STRATEGY_POD_DEFINITIONS)
    }
    return sorted(existing.values(), key=lambda pod: order.get(pod.code, len(order)))


async def _load_latest_snapshots(
    session: AsyncSession,
    pods: list[StrategyPod],
) -> dict[object, StrategyPodSnapshot]:
    if not pods:
        return {}
    pod_ids = [pod.id for pod in pods]
    snapshots = await session.scalars(
        select(StrategyPodSnapshot)
        .where(StrategyPodSnapshot.strategy_pod_id.in_(pod_ids))
        .order_by(StrategyPodSnapshot.captured_at.desc())
    )
    latest: dict[object, StrategyPodSnapshot] = {}
    for snapshot in snapshots:
        latest.setdefault(snapshot.strategy_pod_id, snapshot)
    return latest


async def _load_runtime_context(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> StrategyPodRuntimeContext:
    generated_at = datetime.now(timezone.utc)
    risk_overview = await build_risk_centre_overview(session, user)
    warnings = list(risk_overview.notes)

    try:
        latest_regime = await get_latest_market_regime_model(session)
    except MLTrainingDataUnavailableError as exc:
        latest_regime = None
        warnings.append(str(exc))

    model_comparison = await list_predictive_model_comparison(session, limit=5)
    recent_memos = await list_recent_ticker_memos(session, user, limit=20)
    price_coverage = await _load_market_price_coverage(session)

    return StrategyPodRuntimeContext(
        generated_at=generated_at,
        risk_overview=risk_overview,
        latest_regime=latest_regime,
        model_comparison=model_comparison,
        recent_memos=recent_memos,
        price_coverage=price_coverage,
        warnings=warnings,
    )


async def _load_market_price_coverage(session: AsyncSession) -> MarketPriceCoverage:
    row = (
        await session.execute(
            select(
                func.count(MarketPriceBar.id),
                func.count(func.distinct(MarketPriceBar.instrument_id)),
                func.max(MarketPriceBar.bar_date),
            )
        )
    ).one()
    return MarketPriceCoverage(
        bar_count=int(row[0] or 0),
        instrument_count=int(row[1] or 0),
        latest_bar_date=row[2],
    )


def _pod_response(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
    latest_snapshot: StrategyPodSnapshot | None,
) -> StrategyPodResponse:
    assessment = _assess_pod(pod, context)
    failed_risk_messages = [
        measurement.message
        for measurement in context.risk_overview.measurements
        if not measurement.passed
    ][:5]
    evaluation = {
        **(pod.evaluation or {}),
        "live": assessment.evaluation_overlay,
    }
    current_signals = {
        **(pod.current_signals or {}),
        "latest_evidence": {
            signal.key: signal.model_dump(mode="json")
            for signal in assessment.live_signals
        },
    }

    return StrategyPodResponse(
        id=pod.id,
        code=pod.code,
        name=pod.name,
        mandate=pod.mandate,
        status=pod.status,
        lifecycle_stage=pod.lifecycle_stage,
        capital_allocation_pct=pod.capital_allocation_pct,
        risk_budget_pct=pod.risk_budget_pct,
        volatility_target_pct=pod.volatility_target_pct,
        max_drawdown_pct=pod.max_drawdown_pct,
        turnover_ceiling_pct=pod.turnover_ceiling_pct,
        approved_instruments=pod.approved_instruments or [],
        shutdown_criteria=pod.shutdown_criteria,
        notes=pod.notes,
        current_signals=current_signals,
        evaluation=evaluation,
        live_signals=assessment.live_signals,
        current_signal_score=assessment.current_signal_score,
        model_confidence=assessment.model_confidence,
        risk_level=context.risk_overview.snapshot.risk_level,
        allocation_recommendation=assessment.allocation_recommendation,
        open_risk_warnings=failed_risk_messages,
        latest_snapshot=_latest_snapshot_response(latest_snapshot),
    )


def _assess_pod(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    if pod.code == "macro_regime":
        return _assess_macro_regime(pod, context)
    if pod.code == "cross_asset_trend":
        return _assess_cross_asset_trend(pod, context)
    if pod.code == "quant_equity":
        return _assess_quant_equity(pod, context)
    if pod.code == "fundamental_equity":
        return _assess_fundamental_equity(pod, context)
    if pod.code == "relative_value":
        return _assess_relative_value(pod, context)
    return _assess_experimental_research(pod, context)


def _assess_macro_regime(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    if context.latest_regime is None:
        signals = [
            StrategyPodSignalResponse(
                key="regime_model",
                label="Regime Model",
                value="Pending",
                status="pending",
                detail="Fit the HMM regime model before this pod can guide allocation.",
            )
        ]
        score = Decimal("35.0000")
        confidence = Decimal("0.0000")
        regime = None
    else:
        regime = context.latest_regime.current_regime
        confidence = _pct(context.latest_regime.confidence_score)
        score = _macro_regime_score(regime, confidence)
        signals = [
            StrategyPodSignalResponse(
                key="current_regime",
                label="Current Regime",
                value=_label(regime),
                status="live",
                detail=f"{context.latest_regime.ticker} regime model confidence is {confidence}%.",
                as_of_date=context.latest_regime.as_of_date,
            ),
            StrategyPodSignalResponse(
                key="transition_risk",
                label="Transition Risk",
                value=_transition_risk_label(
                    context.latest_regime.current_regime, confidence
                ),
                status="live",
                detail="Derived from current regime label and model confidence.",
                as_of_date=context.latest_regime.as_of_date,
            ),
        ]

    recommendation = strategy_pod_allocation_recommendation(
        code=pod.code,
        status=pod.status,
        lifecycle_stage=pod.lifecycle_stage,
        risk_level=context.risk_overview.snapshot.risk_level,
        capital_allocation_pct=pod.capital_allocation_pct,
        current_regime=regime,
        current_signal_score=score,
        model_confidence=confidence,
    )
    return StrategyPodAssessment(
        live_signals=signals,
        current_signal_score=score,
        model_confidence=confidence,
        allocation_recommendation=recommendation,
        evaluation_overlay={
            "regime": regime,
            "risk_level": context.risk_overview.snapshot.risk_level,
            "state_count": (
                len(context.latest_regime.state_probabilities)
                if context.latest_regime
                else 0
            ),
        },
    )


def _assess_cross_asset_trend(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    coverage = context.price_coverage
    if coverage.instrument_count == 0:
        score = Decimal("30.0000")
        confidence = Decimal("0.0000")
        status = "pending"
        value = "No price history"
        detail = "Backfill ETF and asset-class proxy prices before trend scoring."
    else:
        score = _pct(Decimal("45") + Decimal(min(coverage.instrument_count * 3, 25)))
        confidence = _pct(
            Decimal("35") + Decimal(min(coverage.instrument_count * 4, 30))
        )
        status = "live" if coverage.instrument_count >= 5 else "warning"
        value = f"{coverage.instrument_count} instruments"
        detail = f"{coverage.bar_count} price bars available for trend research."

    signals = [
        StrategyPodSignalResponse(
            key="price_coverage",
            label="Price Coverage",
            value=value,
            status=status,
            detail=detail,
            as_of_date=coverage.latest_bar_date,
        ),
        StrategyPodSignalResponse(
            key="trend_model",
            label="Trend Model",
            value="Research design",
            status="pending",
            detail="Dedicated moving-average and breakout model is the next implementation step for this pod.",
        ),
    ]
    recommendation = strategy_pod_allocation_recommendation(
        code=pod.code,
        status=pod.status,
        lifecycle_stage=pod.lifecycle_stage,
        risk_level=context.risk_overview.snapshot.risk_level,
        capital_allocation_pct=pod.capital_allocation_pct,
        current_signal_score=score,
        model_confidence=confidence,
    )
    return StrategyPodAssessment(
        live_signals=signals,
        current_signal_score=score,
        model_confidence=confidence,
        allocation_recommendation=recommendation,
        evaluation_overlay={
            "price_bar_count": coverage.bar_count,
            "price_instrument_count": coverage.instrument_count,
            "latest_bar_date": (
                coverage.latest_bar_date.isoformat()
                if coverage.latest_bar_date
                else None
            ),
        },
    )


def _assess_quant_equity(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    latest = context.model_comparison[0] if context.model_comparison else None
    if latest is None:
        score = Decimal("35.0000")
        confidence = Decimal("0.0000")
        signals = [
            StrategyPodSignalResponse(
                key="predictive_model",
                label="Predictive Model",
                value="Pending",
                status="pending",
                detail="Train the relative-return model before quant rankings can drive decisions.",
            )
        ]
    else:
        accuracy = _pct(latest.validation_directional_accuracy)
        validation_rows = latest.validation_rows or 0
        score = _quant_model_score(accuracy, validation_rows)
        confidence = _pct(
            accuracy * Decimal("0.75")
            + Decimal(min(validation_rows, 100)) * Decimal("0.25")
        )
        signals = [
            StrategyPodSignalResponse(
                key="predictive_model",
                label="Predictive Model",
                value=latest.model_version,
                status="live" if validation_rows >= 30 else "warning",
                detail=f"{validation_rows} validation rows; directional accuracy {accuracy}%.",
                as_of_date=latest.created_at.date(),
            ),
            StrategyPodSignalResponse(
                key="downside_proxy",
                label="Downside Proxy",
                value=(
                    f"{latest.residual_p05_pct}%"
                    if latest.residual_p05_pct is not None
                    else "Pending"
                ),
                status="live" if latest.residual_p05_pct is not None else "pending",
                detail="Uses model residual p05 as a first-pass downside proxy.",
                as_of_date=latest.created_at.date(),
            ),
        ]

    recommendation = strategy_pod_allocation_recommendation(
        code=pod.code,
        status=pod.status,
        lifecycle_stage=pod.lifecycle_stage,
        risk_level=context.risk_overview.snapshot.risk_level,
        capital_allocation_pct=pod.capital_allocation_pct,
        current_signal_score=score,
        model_confidence=confidence,
    )
    return StrategyPodAssessment(
        live_signals=signals,
        current_signal_score=score,
        model_confidence=confidence,
        allocation_recommendation=recommendation,
        evaluation_overlay={
            "latest_model_version": latest.model_version if latest else None,
            "validation_rows": latest.validation_rows if latest else 0,
            "directional_accuracy": (
                str(latest.validation_directional_accuracy) if latest else None
            ),
            "models_tracked": len(context.model_comparison),
        },
    )


def _assess_fundamental_equity(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    memos = context.recent_memos
    confidence_values = [
        _pct(memo.confidence_score)
        for memo in memos
        if memo.confidence_score is not None
    ]
    composite_values = [
        _pct(memo.composite_score) for memo in memos if memo.composite_score is not None
    ]
    confidence = _average(confidence_values)
    score = _average(composite_values) if composite_values else Decimal("40.0000")
    latest_memo_date = max((memo.memo_date for memo in memos), default=None)
    action_counts = _counts([memo.action or "unclassified" for memo in memos])
    signals = [
        StrategyPodSignalResponse(
            key="recent_memos",
            label="Recent Memos",
            value=str(len(memos)),
            status="live" if memos else "pending",
            detail="Ticker analyst memos are the primary evidence source for this pod.",
            as_of_date=latest_memo_date,
        ),
        StrategyPodSignalResponse(
            key="action_mix",
            label="Action Mix",
            value=_action_mix_label(action_counts),
            status="live" if memos else "pending",
            detail="Latest analyst actions across saved memos.",
            as_of_date=latest_memo_date,
        ),
    ]
    recommendation = strategy_pod_allocation_recommendation(
        code=pod.code,
        status=pod.status,
        lifecycle_stage=pod.lifecycle_stage,
        risk_level=context.risk_overview.snapshot.risk_level,
        capital_allocation_pct=pod.capital_allocation_pct,
        current_signal_score=score,
        model_confidence=confidence,
    )
    return StrategyPodAssessment(
        live_signals=signals,
        current_signal_score=score,
        model_confidence=confidence,
        allocation_recommendation=recommendation,
        evaluation_overlay={
            "memo_count": len(memos),
            "average_composite_score": str(score),
            "average_confidence": str(confidence),
            "action_counts": action_counts,
            "latest_tickers": [memo.ticker for memo in memos[:5]],
        },
    )


def _assess_relative_value(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    pairs = context.risk_overview.correlation_pairs
    score = _pct(Decimal("35") + Decimal(min(len(pairs) * 5, 30)))
    confidence = Decimal("35.0000") if pairs else Decimal("0.0000")
    signals = [
        StrategyPodSignalResponse(
            key="correlation_pairs",
            label="Correlation Pairs",
            value=str(len(pairs)),
            status="live" if pairs else "pending",
            detail="Current portfolio correlation pairs are a first input, not a complete relative-value model.",
            as_of_date=context.risk_overview.snapshot.as_of_date,
        ),
        StrategyPodSignalResponse(
            key="execution_constraints",
            label="Execution Constraints",
            value="Unresolved",
            status="warning",
            detail="Shorting, borrow, leverage, and transaction-cost constraints are not yet modeled.",
        ),
    ]
    recommendation = strategy_pod_allocation_recommendation(
        code=pod.code,
        status=pod.status,
        lifecycle_stage=pod.lifecycle_stage,
        risk_level=context.risk_overview.snapshot.risk_level,
        capital_allocation_pct=pod.capital_allocation_pct,
        current_signal_score=score,
        model_confidence=confidence,
    )
    return StrategyPodAssessment(
        live_signals=signals,
        current_signal_score=score,
        model_confidence=confidence,
        allocation_recommendation=recommendation,
        evaluation_overlay={
            "correlation_pair_count": len(pairs),
            "top_pairs": [pair.model_dump(mode="json") for pair in pairs[:5]],
            "live_capital_allowed": False,
        },
    )


def _assess_experimental_research(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    signal = StrategyPodSignalResponse(
        key="sandbox_governance",
        label="Sandbox Governance",
        value="Research-only",
        status="research",
        detail="Ideas must prove baseline improvement, robustness, and risk fit before graduating.",
        as_of_date=context.risk_overview.snapshot.as_of_date,
    )
    recommendation = strategy_pod_allocation_recommendation(
        code=pod.code,
        status=pod.status,
        lifecycle_stage=pod.lifecycle_stage,
        risk_level=context.risk_overview.snapshot.risk_level,
        capital_allocation_pct=pod.capital_allocation_pct,
        current_signal_score=Decimal("20.0000"),
        model_confidence=Decimal("20.0000"),
    )
    return StrategyPodAssessment(
        live_signals=[signal],
        current_signal_score=Decimal("20.0000"),
        model_confidence=Decimal("20.0000"),
        allocation_recommendation=recommendation,
        evaluation_overlay={
            "live_capital_allowed": False,
            "graduation_gate": "candidate pod review",
        },
    )


def _snapshot_to_response(
    snapshot: StrategyPodSnapshot,
    pod: StrategyPod,
) -> StrategyPodSnapshotResponse:
    return StrategyPodSnapshotResponse(
        snapshot_id=snapshot.id,
        strategy_pod_id=pod.id,
        code=pod.code,
        captured_at=snapshot.captured_at,
        as_of_date=snapshot.as_of_date,
        status=snapshot.status,
        lifecycle_stage=snapshot.lifecycle_stage,
        capital_allocation_pct=snapshot.capital_allocation_pct,
        risk_budget_pct=snapshot.risk_budget_pct,
        current_signal_score=snapshot.current_signal_score,
        model_confidence=snapshot.model_confidence,
        risk_level=snapshot.risk_level,
        allocation_recommendation=snapshot.allocation_recommendation,
    )


def _latest_snapshot_response(
    snapshot: StrategyPodSnapshot | None,
) -> StrategyPodLatestSnapshotResponse | None:
    if snapshot is None:
        return None
    return StrategyPodLatestSnapshotResponse(
        snapshot_id=snapshot.id,
        captured_at=snapshot.captured_at,
        as_of_date=snapshot.as_of_date,
        current_signal_score=snapshot.current_signal_score,
        model_confidence=snapshot.model_confidence,
        risk_level=snapshot.risk_level,
        allocation_recommendation=snapshot.allocation_recommendation,
    )


def _macro_regime_score(regime: str, confidence: Decimal) -> Decimal:
    base_by_regime = {
        "risk-on": Decimal("80"),
        "constructive": Decimal("70"),
        "neutral": Decimal("55"),
        "fragile": Decimal("42"),
        "stress": Decimal("25"),
        "shock": Decimal("15"),
    }
    base = base_by_regime.get(regime, Decimal("45"))
    confidence_adjustment = (confidence - Decimal("50")) * Decimal("0.30")
    return _pct(base + confidence_adjustment)


def _transition_risk_label(regime: str, confidence: Decimal) -> str:
    if regime in {"stress", "shock"}:
        return "High"
    if regime == "fragile" or confidence < Decimal("45"):
        return "Elevated"
    if confidence >= Decimal("65"):
        return "Contained"
    return "Moderate"


def _quant_model_score(
    accuracy: Decimal,
    validation_rows: int,
) -> Decimal:
    row_credit = Decimal(min(validation_rows, 100)) * Decimal("0.20")
    return _pct((accuracy * Decimal("0.80")) + row_credit)


def _average(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0.0000")
    return _decimal4(sum(values, Decimal("0")) / Decimal(len(values)))


def _counts(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = normalize_strategy_pod_code(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _action_mix_label(counts: dict[str, int]) -> str:
    if not counts:
        return "No memos"
    leaders = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:2]
    return ", ".join(f"{_label(key)} {value}" for key, value in leaders)


def _label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _pct(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0.0000")
    decimal = _decimal4(value)
    if decimal < 0:
        return Decimal("0.0000")
    if decimal > 100:
        return Decimal("100.0000")
    return decimal


def _decimal4(value: Decimal | int | float | str) -> Decimal:
    try:
        decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        decimal = Decimal("0")
    return decimal.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _json_payload(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_payload(item) for key, item in value.items()}
    return value
