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
from app.services.administration.system_log import record_system_log
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

POD_CATEGORY_ORDER = ["alpha", "hedge", "treasury"]

CANONICAL_SYNC_FIELDS = (
    "name",
    "pod_category",
    "live_scope",
    "mandate",
    "approved_instruments",
    "current_signals",
    "evaluation",
    "shutdown_criteria",
    "notes",
)

DEFAULT_STRATEGY_POD_DEFINITIONS = [
    {
        "code": "macro_regime",
        "name": "Regime-Aware Global Macro",
        "pod_category": "alpha",
        "live_scope": "yes",
        "mandate": "Allocate capital according to changing macroeconomic and market regimes.",
        "status": "active",
        "lifecycle_stage": "paper_trading",
        "capital_allocation_pct": Decimal("25.0000"),
        "risk_budget_pct": Decimal("22.0000"),
        "volatility_target_pct": Decimal("12.0000"),
        "max_drawdown_pct": Decimal("10.0000"),
        "turnover_ceiling_pct": Decimal("50.0000"),
        "approved_instruments": [
            "SPY",
            "QQQ",
            "IWM",
            "TLT",
            "IEF",
            "SHY",
            "GLD",
            "DBC",
            "cash",
        ],
        "current_signals": {
            "primary_model": "HMM market regime model",
            "regime_framework": "growth x inflation with volatility overlay",
            "required_inputs": [
                "economic growth",
                "inflation",
                "interest rates",
                "yield curve",
                "credit conditions",
                "market volatility",
                "USD strength",
                "commodities",
                "liquidity",
                "market breadth",
            ],
        },
        "evaluation": {
            "primary_question": "What economic environment are we in, and which assets are likely to perform best under that environment?",
            "minimum_evidence": [
                "regime probability",
                "transition risk",
                "macro bias recommendation",
                "risk-centre agreement",
            ],
        },
        "shutdown_criteria": "Suspend if regime state is unstable, confidence collapses, or risk centre enters halt.",
        "notes": "Phase-one version uses price and volatility until full macro datasets are connected.",
    },
    {
        "code": "cross_asset_trend",
        "name": "Cross-Asset Trend Following",
        "pod_category": "alpha",
        "live_scope": "yes",
        "mandate": "Capture persistent directional movements across liquid equity, bond, gold, and commodity markets.",
        "status": "watch",
        "lifecycle_stage": "research",
        "capital_allocation_pct": Decimal("20.0000"),
        "risk_budget_pct": Decimal("18.0000"),
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
            "horizons": ["1M", "3M", "6M", "12M"],
            "required_inputs": [
                "moving-average trend",
                "breakouts",
                "relative strength",
                "trend persistence",
                "volatility-adjusted momentum",
            ],
        },
        "evaluation": {
            "primary_question": "Which markets are displaying statistically persistent trends?",
            "minimum_evidence": [
                "multi-horizon agreement",
                "volatility scaling",
                "transaction-cost-aware backtest",
            ],
        },
        "shutdown_criteria": "Suspend if trend turnover overwhelms expected edge or correlations spike.",
        "notes": "Dedicated trend model is the next implementation step; price history is already available.",
    },
    {
        "code": "quant_equity",
        "name": "Quantitative Equity Ranking",
        "pod_category": "alpha",
        "live_scope": "yes",
        "mandate": "Systematically identify the strongest securities within the investable equity universe.",
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
            "primary_model": "weighted factor + ridge/logistic relative-return model",
            "factor_families": [
                "quality",
                "value",
                "momentum",
                "growth",
                "revisions",
                "sentiment",
                "risk",
            ],
            "deployment_mode": "long_only",
        },
        "evaluation": {
            "primary_question": "Which available companies are most attractive relative to the other companies we could own?",
            "minimum_evidence": [
                "validation rows",
                "directional accuracy",
                "factor transparency",
                "simple-model baseline comparison",
            ],
        },
        "shutdown_criteria": "Disable if validation accuracy decays or residual downside becomes unacceptable.",
        "notes": "High-ranking names feed Ticker Analyst for deeper research before live deployment.",
    },
    {
        "code": "fundamental_equity",
        "name": "Fundamental / Catalyst Equity",
        "pod_category": "alpha",
        "live_scope": "yes",
        "mandate": "Identify securities where market expectations differ materially from underlying business reality.",
        "status": "active",
        "lifecycle_stage": "probationary_capital",
        "capital_allocation_pct": Decimal("20.0000"),
        "risk_budget_pct": Decimal("20.0000"),
        "volatility_target_pct": Decimal("18.0000"),
        "max_drawdown_pct": Decimal("15.0000"),
        "turnover_ceiling_pct": Decimal("35.0000"),
        "approved_instruments": ["US-listed equities", "NGX equities", "liquid ETFs"],
        "current_signals": {
            "primary_model": "AI-assisted ticker analyst memo",
            "thesis_fields": [
                "market expectation",
                "our view",
                "catalyst",
                "base case",
                "bull case",
                "bear case",
                "thesis breakers",
            ],
        },
        "evaluation": {
            "primary_question": "What does the market appear to believe, and where might that belief be wrong?",
            "minimum_evidence": [
                "complete memo",
                "catalyst path",
                "thesis breakers",
                "portfolio fit",
            ],
        },
        "shutdown_criteria": "Stop adding names if thesis quality weakens or downside cases are not explicit.",
        "notes": "First live alpha book. Ticker Analyst is the primary evidence source.",
    },
    {
        "code": "relative_value",
        "name": "Relative Value / Capital Rotation",
        "pod_category": "alpha",
        "live_scope": "limited",
        "mandate": "Find opportunities when capital, relative strength, or economic value shifts from one asset, company, or industry toward another.",
        "status": "research",
        "lifecycle_stage": "research",
        "capital_allocation_pct": Decimal("10.0000"),
        "risk_budget_pct": Decimal("8.0000"),
        "volatility_target_pct": Decimal("12.0000"),
        "max_drawdown_pct": Decimal("8.0000"),
        "turnover_ceiling_pct": Decimal("120.0000"),
        "approved_instruments": [
            "pairs",
            "sector-relative baskets",
            "ETF relationships",
            "Market Radar rotation candidates",
        ],
        "current_signals": {
            "primary_model": "relationship and capital-rotation diagnostics",
            "relationship_types": [
                "competitor",
                "input-cost",
                "sector rotation",
                "FX",
                "supply chain",
                "macro",
            ],
        },
        "evaluation": {
            "primary_question": "If something is losing, who benefits?",
            "minimum_evidence": [
                "relationship evidence",
                "historical pattern sample",
                "current confirmation",
                "research priority label",
            ],
        },
        "shutdown_criteria": "Limited live scope until shorting, borrow, and execution constraints are modeled.",
        "notes": "Closely integrated with Market Radar. Research candidates only until constraints are resolved.",
    },
    {
        "code": "central_hedge_engine",
        "name": "Central Hedge Engine",
        "pod_category": "hedge",
        "live_scope": "yes",
        "mandate": "Remove unintended portfolio risks that are not part of the fund's investment thesis.",
        "status": "active",
        "lifecycle_stage": "core_strategy",
        "capital_allocation_pct": Decimal("0.0000"),
        "risk_budget_pct": Decimal("15.0000"),
        "volatility_target_pct": None,
        "max_drawdown_pct": None,
        "turnover_ceiling_pct": Decimal("60.0000"),
        "approved_instruments": [
            "cash",
            "short-duration Treasuries",
            "Treasury ETFs",
            "GLD",
            "dynamic exposure reduction",
        ],
        "current_signals": {
            "hedge_strategies": [
                "cash_treasury_reserve",
                "diversifying_assets",
                "dynamic_exposure_reduction",
            ],
            "research_only": [
                "market_beta_hedge",
                "sector_hedge",
                "pair_relative_value_hedge",
                "fx_hedge",
                "volatility_tail_hedge",
                "factor_hedge",
            ],
            "exposure_classes": ["intentional", "unintentional", "hedge"],
        },
        "evaluation": {
            "primary_question": "Which risks are intentional and which risks are accidental?",
            "minimum_evidence": [
                "exposure classification",
                "simplest effective hedge",
                "stress test",
            ],
        },
        "shutdown_criteria": "Never use a complicated hedge when reducing the underlying position is better.",
        "notes": "Alpha generates return; hedging removes risks we never intended to take.",
    },
    {
        "code": "treasury_reserve",
        "name": "Treasury Reserve",
        "pod_category": "treasury",
        "live_scope": "yes",
        "mandate": "Maintain active cash and short-duration Treasury liquidity as a portfolio risk dial.",
        "status": "active",
        "lifecycle_stage": "core_strategy",
        "capital_allocation_pct": Decimal("15.0000"),
        "risk_budget_pct": Decimal("5.0000"),
        "volatility_target_pct": Decimal("2.0000"),
        "max_drawdown_pct": Decimal("1.0000"),
        "turnover_ceiling_pct": Decimal("25.0000"),
        "approved_instruments": [
            "cash",
            "short-duration Treasuries",
            "SHY",
            "IEF",
        ],
        "current_signals": {
            "primary_model": "active cash allocation",
            "increase_cash_when": [
                "opportunity quality falls",
                "risk rises",
                "correlations rise",
                "volatility rises",
                "model confidence falls",
            ],
        },
        "evaluation": {
            "primary_question": "How much dry powder should the portfolio hold right now?",
            "minimum_evidence": [
                "cash versus target",
                "opportunity set quality",
                "portfolio risk level",
            ],
        },
        "shutdown_criteria": "Treasury reserve is always active; only the target level changes.",
        "notes": "Cash is an active allocation, not idle capital.",
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
    alpha_pods = [item for item in responses if item.pod_category == "alpha"]
    hedge_pods = [item for item in responses if item.pod_category == "hedge"]
    treasury_pods = [item for item in responses if item.pod_category == "treasury"]
    alpha_allocation_total = _decimal4(
        sum((pod.capital_allocation_pct for pod in alpha_pods), Decimal("0"))
    )
    treasury_target = _decimal4(
        sum((pod.capital_allocation_pct for pod in treasury_pods), Decimal("0"))
    )
    allocation_total = _decimal4(
        sum((pod.capital_allocation_pct for pod in responses), Decimal("0"))
    )
    risk_budget_total = _decimal4(
        sum((pod.risk_budget_pct for pod in responses), Decimal("0"))
    )
    unallocated = _decimal4(max(Decimal("0"), Decimal("100") - alpha_allocation_total))
    warnings: list[str] = list(context.warnings)
    if alpha_allocation_total > Decimal("100"):
        warnings.append(
            "Alpha pod allocation is above 100%; CIO review required."
        )
    if allocation_total > Decimal("115"):
        warnings.append(
            "Total book targets including treasury exceed 115%; review capital stack."
        )

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
        cash_pct=context.risk_overview.snapshot.cash_pct,
        allocation_total_pct=allocation_total,
        alpha_allocation_total_pct=alpha_allocation_total,
        treasury_target_pct=treasury_target,
        risk_budget_total_pct=risk_budget_total,
        unallocated_pct=unallocated,
        alpha_pods=alpha_pods,
        hedge_pods=hedge_pods,
        treasury_pods=treasury_pods,
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

    await record_system_log(
        session,
        owner_user_id=user.id,
        category="strategy_pods",
        event="strategy_pod_updated",
        message=f"{pod.name} controls updated ({pod.status}).",
        context={"pod_code": pod.code, "status": pod.status},
    )
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
    await session.flush()
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="strategy_pods",
        event="strategy_pod_snapshot_captured",
        message=f"Snapshot captured for {pod.name}.",
        context={"pod_code": pod.code, "snapshot_id": str(snapshot.id)},
    )
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
    if normalized_code == "relative_value" and lifecycle_stage == "research":
        return "Limited live scope; capital rotation ideas require Radar confirmation and research review."

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
    synced = False
    definitions_by_code = {
        definition["code"]: definition for definition in DEFAULT_STRATEGY_POD_DEFINITIONS
    }

    for definition in DEFAULT_STRATEGY_POD_DEFINITIONS:
        if definition["code"] in existing:
            continue
        pod = StrategyPod(owner_user_id=user.id, **definition)
        session.add(pod)
        existing[pod.code] = pod
        created = True

    for code, definition in definitions_by_code.items():
        pod = existing.get(code)
        if pod is None:
            continue
        for field_name in CANONICAL_SYNC_FIELDS:
            if field_name not in definition:
                continue
            setattr(pod, field_name, definition[field_name])
            synced = True

    if created or synced:
        await session.commit()
        if created:
            logger.info(
                "strategy_pods_seeded",
                extra={
                    "owner_user_id": user.id,
                    "pod_count": len(DEFAULT_STRATEGY_POD_DEFINITIONS),
                },
            )
        if synced:
            logger.info(
                "strategy_pods_synced",
                extra={
                    "owner_user_id": user.id,
                    "canonical_pod_count": len(definitions_by_code),
                },
            )

    order = {
        definition["code"]: index
        for index, definition in enumerate(DEFAULT_STRATEGY_POD_DEFINITIONS)
    }

    def sort_key(pod: StrategyPod) -> tuple[int, int, str]:
        category_rank = (
            POD_CATEGORY_ORDER.index(pod.pod_category)
            if pod.pod_category in POD_CATEGORY_ORDER
            else len(POD_CATEGORY_ORDER)
        )
        if pod.pod_category == "alpha":
            return (category_rank, order.get(pod.code, len(order)), pod.code)
        return (category_rank, 0, pod.code)

    active_pods = [
        pod
        for pod in existing.values()
        if pod.code in definitions_by_code or pod.status != "retired"
    ]
    return sorted(active_pods, key=sort_key)


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
        pod_category=pod.pod_category,
        live_scope=pod.live_scope,
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
        return _assess_capital_rotation(pod, context)
    if pod.code == "central_hedge_engine":
        return _assess_hedge_engine(pod, context)
    if pod.code == "treasury_reserve":
        return _assess_treasury_reserve(pod, context)
    return _assess_legacy_pod(pod, context)


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


def _assess_capital_rotation(
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
            value="Limited live scope",
            status="warning",
            detail="Pairs, shorts, and leverage remain research-only. Radar rotation ideas become research candidates.",
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
            "live_capital_allowed": pod.live_scope == "yes",
        },
    )


def _assess_hedge_engine(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    snapshot = context.risk_overview.snapshot
    failed_checks = [
        measurement.message
        for measurement in context.risk_overview.measurements
        if not measurement.passed
    ]
    gross = snapshot.gross_exposure_pct
    net = snapshot.net_exposure_pct
    score = _pct(Decimal("55") - min(abs(net) / Decimal("2"), Decimal("20")))
    confidence = _pct(Decimal("50") + Decimal(min(len(failed_checks) * 8, 30)))
    signals = [
        StrategyPodSignalResponse(
            key="gross_exposure",
            label="Gross Exposure",
            value=f"{gross}%",
            status="live",
            detail="Monitor unintended market beta before adding explicit hedges.",
            as_of_date=snapshot.as_of_date,
        ),
        StrategyPodSignalResponse(
            key="net_exposure",
            label="Net Exposure",
            value=f"{net}%",
            status="live",
            detail="Net beta is the first hedge input when security selection is the thesis.",
            as_of_date=snapshot.as_of_date,
        ),
        StrategyPodSignalResponse(
            key="active_hedges",
            label="Active Hedges",
            value="Cash / Treasury / dynamic reduction",
            status="live",
            detail="Index shorts, sector shorts, FX, and tail hedges remain research-only.",
            as_of_date=snapshot.as_of_date,
        ),
    ]
    recommendation = (
        "Increase cash or Treasuries until unintended exposures are classified."
        if failed_checks
        else "Hedge book active; prefer the simplest effective hedge before complex instruments."
    )
    return StrategyPodAssessment(
        live_signals=signals,
        current_signal_score=score,
        model_confidence=confidence,
        allocation_recommendation=recommendation,
        evaluation_overlay={
            "failed_risk_checks": len(failed_checks),
            "gross_exposure_pct": str(gross),
            "net_exposure_pct": str(net),
            "research_only_hedges": [
                "market_beta",
                "sector",
                "pair_relative_value",
                "fx",
                "volatility_tail",
                "factor",
            ],
        },
    )


def _assess_treasury_reserve(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    snapshot = context.risk_overview.snapshot
    target = pod.capital_allocation_pct
    actual = snapshot.cash_pct
    gap = _decimal4(target - actual)
    score = _pct(
        Decimal("100")
        - min(abs(gap) * Decimal("2"), Decimal("40"))
    )
    confidence = _pct(Decimal("70"))
    if gap > 0:
        recommendation = (
            f"Raise cash toward the {target}% treasury target; current cash is {actual}%."
        )
    elif gap < 0:
        recommendation = (
            f"Cash is above the {target}% target; deploy only into approved alpha opportunities."
        )
    else:
        recommendation = "Treasury reserve is on target."
    signals = [
        StrategyPodSignalResponse(
            key="cash_target",
            label="Cash Target",
            value=f"{target}%",
            status="live",
            detail="Cash is an active allocation, not idle capital.",
            as_of_date=snapshot.as_of_date,
        ),
        StrategyPodSignalResponse(
            key="cash_actual",
            label="Cash Actual",
            value=f"{actual}%",
            status="live" if abs(gap) <= Decimal("3") else "warning",
            detail=f"Gap to target: {gap}%.",
            as_of_date=snapshot.as_of_date,
        ),
    ]
    return StrategyPodAssessment(
        live_signals=signals,
        current_signal_score=score,
        model_confidence=confidence,
        allocation_recommendation=recommendation,
        evaluation_overlay={
            "cash_target_pct": str(target),
            "cash_actual_pct": str(actual),
            "cash_gap_pct": str(gap),
        },
    )


def _assess_legacy_pod(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    signal = StrategyPodSignalResponse(
        key="legacy_pod",
        label="Legacy Pod",
        value="Retired or unmapped",
        status="research",
        detail="This pod is outside the current Strategy & Hedging Scope.",
        as_of_date=context.risk_overview.snapshot.as_of_date,
    )
    recommendation = "No live allocation; migrate ideas to Research Lab or an active alpha pod."
    return StrategyPodAssessment(
        live_signals=[signal],
        current_signal_score=Decimal("0.0000"),
        model_confidence=Decimal("0.0000"),
        allocation_recommendation=recommendation,
        evaluation_overlay={"live_capital_allowed": False},
    )


def _assess_experimental_research(
    pod: StrategyPod,
    context: StrategyPodRuntimeContext,
) -> StrategyPodAssessment:
    return _assess_legacy_pod(pod, context)


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
