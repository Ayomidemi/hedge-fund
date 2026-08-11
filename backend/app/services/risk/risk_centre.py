import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import sqrt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import AuthenticatedUser
from app.api.schemas.operating_core import InstrumentCreate
from app.api.schemas.risk_centre import (
    CorrelationPairResponse,
    PreTradeRiskCheckCreate,
    PreTradeRiskCheckResponse,
    RiskCentreOverviewResponse,
    RiskExposureBucketResponse,
    RiskMeasurementResponse,
    RiskPolicyLimitResponse,
    RiskPolicyResponse,
    RiskPositionResponse,
    RiskSnapshotCaptureResponse,
    RiskSnapshotResponse,
    StressScenarioCreate,
    StressTestResultResponse,
)
from app.models import (
    CashLedgerEntry,
    Instrument,
    MarketPriceBar,
    Portfolio,
    PortfolioRiskSnapshot,
    Position,
    PositionRiskSnapshot,
    RiskMeasurement,
    RiskPolicyVersion,
    StressScenario,
    StressTestResult,
)
from app.services.administration.system_log import record_system_log
from app.services.portfolio.calculations import money, percent
from app.services.portfolio.operating_core import get_or_create_default_portfolio

logger = logging.getLogger(__name__)

RISK_POLICY_NAME = "Pease Capital Phase One Risk Policy"
RISK_POLICY_VERSION = "2026.08"
BENCHMARK_TICKER = "SPY"

RISK_HIERARCHY = [
    "normal",
    "warning",
    "reduce",
    "suspend",
    "defensive",
    "halt",
]

DEFAULT_POLICY_LIMITS = [
    {
        "key": "max_single_equity_position_pct",
        "label": "Maximum single-equity position",
        "threshold_value": "5",
        "unit": "percent",
        "scope": "position",
        "severity": "warning",
        "direction": "lte",
        "description": "No single equity should exceed 5% of NAV without review.",
    },
    {
        "key": "max_etf_position_pct",
        "label": "Maximum ETF position",
        "threshold_value": "25",
        "unit": "percent",
        "scope": "position",
        "severity": "warning",
        "direction": "lte",
        "description": "ETF exposure can be larger, but still capped in phase one.",
    },
    {
        "key": "max_sector_exposure_pct",
        "label": "Maximum sector exposure",
        "threshold_value": "30",
        "unit": "percent",
        "scope": "portfolio",
        "severity": "reduce",
        "direction": "lte",
        "description": "Sector concentration above 30% requires reduction or explicit approval.",
    },
    {
        "key": "min_cash_allocation_pct",
        "label": "Minimum cash allocation",
        "threshold_value": "15",
        "unit": "percent",
        "scope": "portfolio",
        "severity": "warning",
        "direction": "gte",
        "description": "The initial mandate keeps at least 15% cash available.",
    },
    {
        "key": "max_gross_exposure_pct",
        "label": "Maximum gross exposure",
        "threshold_value": "100",
        "unit": "percent",
        "scope": "portfolio",
        "severity": "halt",
        "direction": "lte",
        "description": "Phase one does not allow leverage.",
    },
    {
        "key": "max_top5_concentration_pct",
        "label": "Maximum top-5 concentration",
        "threshold_value": "60",
        "unit": "percent",
        "scope": "portfolio",
        "severity": "reduce",
        "direction": "lte",
        "description": "The top five positions should not dominate the fund.",
    },
    {
        "key": "max_portfolio_volatility_pct",
        "label": "Maximum annualized volatility",
        "threshold_value": "30",
        "unit": "percent",
        "scope": "portfolio",
        "severity": "warning",
        "direction": "lte",
        "description": "Volatility above 30% is outside the phase-one comfort band.",
    },
    {
        "key": "max_var_95_pct",
        "label": "Maximum 95% daily VaR",
        "threshold_value": "4",
        "unit": "percent",
        "scope": "portfolio",
        "severity": "reduce",
        "direction": "lte_abs",
        "description": "Historical 95% one-day VaR should stay below 4% of NAV.",
    },
    {
        "key": "max_expected_shortfall_95_pct",
        "label": "Maximum 95% expected shortfall",
        "threshold_value": "6",
        "unit": "percent",
        "scope": "portfolio",
        "severity": "reduce",
        "direction": "lte_abs",
        "description": "Average tail loss should stay below 6% of NAV.",
    },
    {
        "key": "max_liquidity_days",
        "label": "Maximum liquidity days",
        "threshold_value": "5",
        "unit": "days",
        "scope": "position",
        "severity": "warning",
        "direction": "lte",
        "description": "Largest estimated liquidation window should stay under five days.",
    },
]


@dataclass(frozen=True)
class RiskPosition:
    instrument_id: object | None
    ticker: str
    name: str
    asset_class: str
    sector: str | None
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal

    @property
    def exposure_value(self) -> Decimal:
        return abs(self.market_value)


@dataclass(frozen=True)
class PortfolioRiskState:
    portfolio_id: object
    portfolio_name: str
    calculated_at: datetime
    as_of_date: date
    nav: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    positions: list[RiskPosition]


@dataclass(frozen=True)
class PositionMarketStats:
    volatility_pct: Decimal | None = None
    beta_to_benchmark: Decimal | None = None
    liquidity_days: Decimal | None = None


@dataclass(frozen=True)
class PortfolioMarketStats:
    portfolio_volatility_pct: Decimal | None = None
    beta_to_benchmark: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    var_95_pct: Decimal | None = None
    expected_shortfall_95_pct: Decimal | None = None
    liquidity_days: Decimal | None = None
    position_stats: dict[str, PositionMarketStats] | None = None
    correlation_pairs: list[CorrelationPairResponse] | None = None
    notes: list[str] | None = None


async def build_risk_centre_overview(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> RiskCentreOverviewResponse:
    state, price_histories = await _load_current_state(session, user)
    return build_risk_overview_from_state(state, price_histories)


async def capture_risk_snapshot(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> RiskSnapshotCaptureResponse:
    state, price_histories = await _load_current_state(session, user)
    overview = build_risk_overview_from_state(state, price_histories)
    policy_version = await _get_or_create_policy_version(session)

    snapshot_record = PortfolioRiskSnapshot(
        portfolio_id=state.portfolio_id,
        risk_policy_version_id=policy_version.id,
        captured_at=overview.snapshot.calculated_at,
        as_of_date=overview.snapshot.as_of_date,
        nav=overview.snapshot.nav,
        cash_balance=overview.snapshot.cash_balance,
        invested_value=overview.snapshot.invested_value,
        gross_exposure_pct=overview.snapshot.gross_exposure_pct,
        net_exposure_pct=overview.snapshot.net_exposure_pct,
        cash_pct=overview.snapshot.cash_pct,
        top_position_pct=overview.snapshot.top_position_pct,
        top5_concentration_pct=overview.snapshot.top5_concentration_pct,
        portfolio_volatility_pct=overview.snapshot.portfolio_volatility_pct,
        beta_to_benchmark=overview.snapshot.beta_to_benchmark,
        max_drawdown_pct=overview.snapshot.max_drawdown_pct,
        var_95_pct=overview.snapshot.var_95_pct,
        expected_shortfall_95_pct=overview.snapshot.expected_shortfall_95_pct,
        liquidity_days=overview.snapshot.liquidity_days,
        risk_level=overview.snapshot.risk_level,
        exposures={
            "asset_class": [
                item.model_dump(mode="json") for item in overview.asset_class_exposure
            ],
            "sector": [
                item.model_dump(mode="json") for item in overview.sector_exposure
            ],
        },
        payload=overview.model_dump(mode="json"),
    )
    session.add(snapshot_record)
    await session.flush()

    for position in overview.positions:
        if position.instrument_id is None:
            continue
        session.add(
            PositionRiskSnapshot(
                portfolio_risk_snapshot_id=snapshot_record.id,
                portfolio_id=state.portfolio_id,
                instrument_id=position.instrument_id,
                ticker=position.ticker,
                name=position.name,
                asset_class=position.asset_class,
                sector=position.sector,
                quantity=position.quantity,
                market_value=position.market_value,
                weight_pct=position.weight_pct,
                volatility_pct=position.volatility_pct,
                beta_to_benchmark=position.beta_to_benchmark,
                liquidity_days=position.liquidity_days,
                payload=position.model_dump(mode="json"),
            )
        )

    for measurement in overview.measurements:
        session.add(
            RiskMeasurement(
                portfolio_id=state.portfolio_id,
                portfolio_risk_snapshot_id=snapshot_record.id,
                measured_at=overview.snapshot.calculated_at,
                measurement_type=measurement.measurement_type,
                name=measurement.name,
                value=measurement.value,
                unit=measurement.unit,
                threshold_value=measurement.threshold_value,
                passed=measurement.passed,
                severity=measurement.severity,
                message=measurement.message,
                payload=measurement.model_dump(mode="json"),
            )
        )

    for stress in overview.stress_tests:
        session.add(
            StressTestResult(
                portfolio_id=state.portfolio_id,
                portfolio_risk_snapshot_id=snapshot_record.id,
                stress_scenario_id=None,
                run_at=overview.snapshot.calculated_at,
                scenario_name=stress.scenario_name,
                nav_before=stress.nav_before,
                nav_after=stress.nav_after,
                nav_impact_pct=stress.nav_impact_pct,
                severity=stress.severity,
                worst_positions={"positions": stress.worst_positions},
                result_payload=stress.model_dump(mode="json"),
            )
        )

    await record_system_log(
        session,
        owner_user_id=user.id,
        category="risk",
        event="risk_snapshot_captured",
        message=f"Risk snapshot captured — {overview.snapshot.risk_level}.",
        context={
            "snapshot_id": str(snapshot_record.id),
            "risk_level": overview.snapshot.risk_level,
            "measurement_count": len(overview.measurements),
        },
    )
    await session.commit()

    logger.info(
        "risk_snapshot_captured",
        extra={
            "portfolio_id": str(state.portfolio_id),
            "owner_user_id": user.id,
            "snapshot_id": str(snapshot_record.id),
            "risk_level": overview.snapshot.risk_level,
            "measurement_count": len(overview.measurements),
        },
    )

    return RiskSnapshotCaptureResponse(
        snapshot_id=snapshot_record.id,
        captured_at=overview.snapshot.calculated_at,
        measurement_count=len(overview.measurements),
        position_count=len(overview.positions),
        stress_result_count=len(overview.stress_tests),
    )


async def run_custom_stress_test(
    session: AsyncSession,
    payload: StressScenarioCreate,
    user: AuthenticatedUser,
) -> StressTestResultResponse:
    state, _ = await _load_current_state(session, user)
    scenario = _custom_scenario_from_payload(payload)
    result = run_stress_scenario(state, scenario)

    scenario_record = StressScenario(
        owner_user_id=user.id,
        name=payload.name,
        scenario_type="custom",
        shocks=_json_payload(scenario),
        is_system=False,
        notes=payload.notes,
    )
    session.add(scenario_record)
    await session.flush()
    session.add(
        StressTestResult(
            portfolio_id=state.portfolio_id,
            portfolio_risk_snapshot_id=None,
            stress_scenario_id=scenario_record.id,
            run_at=datetime.now(timezone.utc),
            scenario_name=result.scenario_name,
            nav_before=result.nav_before,
            nav_after=result.nav_after,
            nav_impact_pct=result.nav_impact_pct,
            severity=result.severity,
            worst_positions={"positions": result.worst_positions},
            result_payload=result.model_dump(mode="json"),
        )
    )
    await record_system_log(
        session,
        owner_user_id=user.id,
        category="risk",
        event="stress_test_completed",
        message=f"Stress test \"{payload.name}\" completed ({result.nav_impact_pct}% NAV impact).",
        context={
            "scenario_name": payload.name,
            "nav_impact_pct": str(result.nav_impact_pct),
        },
    )
    await session.commit()

    logger.info(
        "custom_stress_test_completed",
        extra={
            "portfolio_id": str(state.portfolio_id),
            "owner_user_id": user.id,
            "scenario_name": payload.name,
            "impact_pct": str(result.nav_impact_pct),
        },
    )
    return result


async def check_pre_trade_risk(
    session: AsyncSession,
    payload: PreTradeRiskCheckCreate,
    user: AuthenticatedUser,
) -> PreTradeRiskCheckResponse:
    state, price_histories = await _load_current_state(session, user)
    pro_forma_state, cash_impact, messages = _apply_trade_to_state(state, payload)
    overview = build_risk_overview_from_state(pro_forma_state, price_histories)
    failed_checks = [check for check in overview.measurements if not check.passed]
    decision = _pre_trade_decision(
        overview.snapshot.risk_level, failed_checks, messages
    )

    await record_system_log(
        session,
        owner_user_id=user.id,
        category="risk",
        event="pre_trade_check",
        message=f"Pre-trade check for {payload.instrument.ticker}: {decision}.",
        context={
            "ticker": payload.instrument.ticker,
            "side": payload.side,
            "decision": decision,
            "risk_level": overview.snapshot.risk_level,
        },
    )
    await session.commit()

    logger.info(
        "pre_trade_risk_checked",
        extra={
            "ticker": payload.instrument.ticker,
            "owner_user_id": user.id,
            "side": payload.side,
            "decision": decision,
            "risk_level": overview.snapshot.risk_level,
            "failed_check_count": len(failed_checks),
        },
    )

    return PreTradeRiskCheckResponse(
        decision=decision,
        risk_level=overview.snapshot.risk_level,
        cash_impact=cash_impact,
        pro_forma_snapshot=overview.snapshot,
        checks=overview.measurements,
        stress_tests=overview.stress_tests,
        messages=messages,
    )


def build_risk_overview_from_state(
    state: PortfolioRiskState,
    price_histories: dict[str, list[MarketPriceBar]] | None = None,
) -> RiskCentreOverviewResponse:
    histories = price_histories or {}
    policy = default_policy_response()
    market_stats = compute_portfolio_market_stats(state, histories)
    position_responses = _position_responses(state, market_stats)
    asset_class_exposure = _exposure_buckets(
        state.positions,
        state.nav,
        key_fn=lambda position: position.asset_class,
    )
    sector_exposure = _exposure_buckets(
        state.positions,
        state.nav,
        key_fn=lambda position: position.sector or "Unclassified",
    )
    measurements = evaluate_risk_policy(
        state,
        market_stats,
        asset_class_exposure=asset_class_exposure,
        sector_exposure=sector_exposure,
    )
    risk_level = risk_level_from_measurements(measurements)
    snapshot = _snapshot_response(
        state,
        market_stats,
        risk_level=risk_level,
    )
    stress_tests = [
        run_stress_scenario(state, scenario)
        for scenario in standard_stress_scenarios(state)
    ]
    notes = list(market_stats.notes or [])
    if not state.positions:
        notes.append("No open positions; market risk is cash-only.")

    return RiskCentreOverviewResponse(
        snapshot=snapshot,
        policy=policy,
        positions=position_responses,
        measurements=measurements,
        stress_tests=stress_tests,
        correlation_pairs=market_stats.correlation_pairs or [],
        asset_class_exposure=asset_class_exposure,
        sector_exposure=sector_exposure,
        notes=notes,
    )


def compute_portfolio_market_stats(
    state: PortfolioRiskState,
    price_histories: dict[str, list[MarketPriceBar]],
) -> PortfolioMarketStats:
    notes: list[str] = []
    returns_by_ticker = {
        ticker: _returns_by_date(bars)
        for ticker, bars in price_histories.items()
        if len(bars) >= 3
    }
    weights = {
        position.ticker: float(position.market_value / state.nav)
        for position in state.positions
        if state.nav > 0 and position.market_value != 0
    }
    portfolio_returns = _portfolio_returns(weights, returns_by_ticker)
    benchmark_returns = returns_by_ticker.get(BENCHMARK_TICKER, {})
    aligned_portfolio, aligned_benchmark = _align_series(
        portfolio_returns, benchmark_returns
    )

    if not portfolio_returns:
        notes.append("Portfolio volatility, VaR, and beta need market price history.")

    position_stats: dict[str, PositionMarketStats] = {}
    for position in state.positions:
        ticker_returns = list(returns_by_ticker.get(position.ticker, {}).values())
        ticker_benchmark, ticker_series = _align_series(
            benchmark_returns,
            returns_by_ticker.get(position.ticker, {}),
        )
        position_stats[position.ticker] = PositionMarketStats(
            volatility_pct=_volatility_pct(ticker_returns),
            beta_to_benchmark=_beta_pct(ticker_series, ticker_benchmark),
            liquidity_days=_liquidity_days(
                position, price_histories.get(position.ticker, [])
            ),
        )

    liquidity_values = [
        stats.liquidity_days
        for stats in position_stats.values()
        if stats.liquidity_days is not None
    ]
    liquidity_days = max(liquidity_values) if liquidity_values else None
    if liquidity_days is None and state.positions:
        notes.append("Liquidity days need recent volume data.")

    return PortfolioMarketStats(
        portfolio_volatility_pct=_volatility_pct(list(portfolio_returns.values())),
        beta_to_benchmark=_beta_pct(aligned_portfolio, aligned_benchmark),
        max_drawdown_pct=_max_drawdown_from_fraction_returns(
            list(portfolio_returns.values())
        ),
        var_95_pct=_var_pct(list(portfolio_returns.values()), percentile=5),
        expected_shortfall_95_pct=_expected_shortfall_pct(
            list(portfolio_returns.values()), percentile=5
        ),
        liquidity_days=liquidity_days,
        position_stats=position_stats,
        correlation_pairs=_correlation_pairs(returns_by_ticker, state.positions),
        notes=notes,
    )


def evaluate_risk_policy(
    state: PortfolioRiskState,
    market_stats: PortfolioMarketStats,
    *,
    asset_class_exposure: list[RiskExposureBucketResponse],
    sector_exposure: list[RiskExposureBucketResponse],
) -> list[RiskMeasurementResponse]:
    metrics = _policy_metric_values(
        state, market_stats, asset_class_exposure, sector_exposure
    )
    checks = []
    for limit in DEFAULT_POLICY_LIMITS:
        value = metrics.get(limit["key"])
        threshold = Decimal(limit["threshold_value"])
        passed = _limit_passed(value, threshold, limit["direction"])
        checks.append(
            RiskMeasurementResponse(
                key=limit["key"],
                name=limit["label"],
                measurement_type=limit["scope"],
                value=value,
                unit=limit["unit"],
                threshold_value=threshold,
                passed=passed,
                severity=limit["severity"] if not passed else "info",
                message=_limit_message(limit, value, threshold, passed),
            )
        )
    return checks


def risk_level_from_measurements(measurements: list[RiskMeasurementResponse]) -> str:
    failed = [measurement for measurement in measurements if not measurement.passed]
    if not failed:
        return "normal"

    severities = {measurement.severity for measurement in failed}
    if "halt" in severities:
        return "halt"
    if "suspend" in severities:
        return "suspend"
    if "reduce" in severities or len(failed) >= 3:
        return "reduce"
    return "warning"


def standard_stress_scenarios(state: PortfolioRiskState) -> list[dict]:
    largest_position = max(
        state.positions, key=lambda item: item.market_value, default=None
    )
    largest_sector = _largest_sector(state)
    scenarios = [
        {
            "name": "Market -5%",
            "scenario_type": "market",
            "market_shock_pct": Decimal("-5"),
            "sector_shocks_pct": {},
            "ticker_shocks_pct": {},
            "cash_shock_pct": Decimal("0"),
            "notes": ["Broad risk-off move across all open positions."],
        },
        {
            "name": "Market -10%",
            "scenario_type": "market",
            "market_shock_pct": Decimal("-10"),
            "sector_shocks_pct": {},
            "ticker_shocks_pct": {},
            "cash_shock_pct": Decimal("0"),
            "notes": ["Severe market drawdown across all open positions."],
        },
        {
            "name": "Market -20%",
            "scenario_type": "market",
            "market_shock_pct": Decimal("-20"),
            "sector_shocks_pct": {},
            "ticker_shocks_pct": {},
            "cash_shock_pct": Decimal("0"),
            "notes": ["Crash scenario for portfolio survival review."],
        },
        {
            "name": "Cash withdrawal -10%",
            "scenario_type": "cash",
            "market_shock_pct": Decimal("0"),
            "sector_shocks_pct": {},
            "ticker_shocks_pct": {},
            "cash_shock_pct": Decimal("-10"),
            "notes": [
                "Liquidity pressure from capital withdrawal or operational need."
            ],
        },
    ]
    if largest_position is not None:
        scenarios.append(
            {
                "name": f"{largest_position.ticker} -25%",
                "scenario_type": "single_name",
                "market_shock_pct": Decimal("0"),
                "sector_shocks_pct": {},
                "ticker_shocks_pct": {largest_position.ticker: Decimal("-25")},
                "cash_shock_pct": Decimal("0"),
                "notes": ["Largest position idiosyncratic shock."],
            }
        )
    if largest_sector is not None:
        scenarios.append(
            {
                "name": f"{largest_sector} -15%",
                "scenario_type": "sector",
                "market_shock_pct": Decimal("0"),
                "sector_shocks_pct": {largest_sector: Decimal("-15")},
                "ticker_shocks_pct": {},
                "cash_shock_pct": Decimal("0"),
                "notes": ["Largest sector shock."],
            }
        )
    return scenarios


def run_stress_scenario(
    state: PortfolioRiskState,
    scenario: dict,
) -> StressTestResultResponse:
    nav_before = state.nav
    stressed_cash = state.cash_balance + (
        state.nav * (_decimal(scenario.get("cash_shock_pct")) / Decimal("100"))
    )
    stressed_positions = []
    for position in state.positions:
        shock = _position_shock(position, scenario)
        stressed_value = money(
            position.market_value * (Decimal("1") + shock / Decimal("100"))
        )
        stressed_positions.append((position, stressed_value, shock))

    nav_after = money(
        stressed_cash + sum((value for _, value, _ in stressed_positions), Decimal("0"))
    )
    nav_impact = money(nav_after - nav_before)
    nav_impact_pct = percent(nav_impact, nav_before)
    worst_positions = sorted(
        [
            {
                "ticker": position.ticker,
                "shock_pct": str(shock),
                "impact": str(money(value - position.market_value)),
                "impact_pct_nav": str(
                    percent(value - position.market_value, nav_before)
                ),
            }
            for position, value, shock in stressed_positions
            if shock != 0
        ],
        key=lambda item: Decimal(item["impact"]),
    )[:5]

    return StressTestResultResponse(
        scenario_name=str(scenario["name"]),
        scenario_type=str(scenario["scenario_type"]),
        nav_before=nav_before,
        nav_after=nav_after,
        nav_impact=nav_impact,
        nav_impact_pct=nav_impact_pct,
        severity=_stress_severity(nav_impact_pct),
        worst_positions=worst_positions,
        notes=[str(note) for note in scenario.get("notes", [])],
    )


async def _load_current_state(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> tuple[PortfolioRiskState, dict[str, list[MarketPriceBar]]]:
    portfolio = await get_or_create_default_portfolio(session, user)
    cash_balance = await _cash_balance(session, portfolio)
    positions = list(
        await session.scalars(
            select(Position)
            .options(selectinload(Position.instrument))
            .where(Position.portfolio_id == portfolio.id)
            .where(Position.quantity > 0)
            .order_by(Position.market_value.desc())
        )
    )
    risk_positions = [
        RiskPosition(
            instrument_id=position.instrument_id,
            ticker=position.instrument.ticker,
            name=position.instrument.name,
            asset_class=position.instrument.asset_class,
            sector=position.instrument.sector,
            quantity=position.quantity,
            average_cost=position.average_cost,
            market_value=position.market_value,
            unrealized_pnl=position.unrealized_pnl,
        )
        for position in positions
    ]
    invested_value = money(
        sum((position.market_value for position in risk_positions), Decimal("0"))
    )
    nav = money(cash_balance + invested_value)
    if nav <= 0:
        nav = Decimal("1.00")
    state = PortfolioRiskState(
        portfolio_id=portfolio.id,
        portfolio_name=portfolio.name,
        calculated_at=datetime.now(timezone.utc),
        as_of_date=date.today(),
        nav=nav,
        cash_balance=cash_balance,
        invested_value=invested_value,
        positions=risk_positions,
    )
    histories = await _load_price_histories(session, risk_positions)
    return state, histories


async def _cash_balance(session: AsyncSession, portfolio: Portfolio) -> Decimal:
    value = await session.scalar(
        select(func.sum(CashLedgerEntry.amount)).where(
            CashLedgerEntry.portfolio_id == portfolio.id
        )
    )
    return money(value or Decimal("0"))


async def _load_price_histories(
    session: AsyncSession,
    positions: list[RiskPosition],
) -> dict[str, list[MarketPriceBar]]:
    tickers = {position.ticker for position in positions}
    tickers.add(BENCHMARK_TICKER)
    instruments = list(
        await session.scalars(select(Instrument).where(Instrument.ticker.in_(tickers)))
    )
    instrument_by_id = {instrument.id: instrument for instrument in instruments}
    if not instrument_by_id:
        return {}
    bars = list(
        await session.scalars(
            select(MarketPriceBar)
            .where(MarketPriceBar.instrument_id.in_(instrument_by_id))
            .where(MarketPriceBar.source == "yahoo")
            .order_by(MarketPriceBar.instrument_id, MarketPriceBar.bar_date)
        )
    )
    histories: dict[str, list[MarketPriceBar]] = {}
    for bar in bars:
        instrument = instrument_by_id[bar.instrument_id]
        histories.setdefault(instrument.ticker, []).append(bar)
    return histories


async def _get_or_create_policy_version(session: AsyncSession) -> RiskPolicyVersion:
    policy = await session.scalar(
        select(RiskPolicyVersion).where(
            RiskPolicyVersion.name == RISK_POLICY_NAME,
            RiskPolicyVersion.version == RISK_POLICY_VERSION,
        )
    )
    if policy is not None:
        return policy
    policy = RiskPolicyVersion(
        name=RISK_POLICY_NAME,
        version=RISK_POLICY_VERSION,
        status="active",
        effective_at=datetime.now(timezone.utc),
        limits={"limits": DEFAULT_POLICY_LIMITS},
        hierarchy={"levels": RISK_HIERARCHY},
        notes="Phase-one policy seeded from the fund scope.",
    )
    session.add(policy)
    await session.flush()
    return policy


def default_policy_response() -> RiskPolicyResponse:
    return RiskPolicyResponse(
        name=RISK_POLICY_NAME,
        version=RISK_POLICY_VERSION,
        status="active",
        hierarchy=RISK_HIERARCHY,
        limits=[
            RiskPolicyLimitResponse(
                key=str(limit["key"]),
                label=str(limit["label"]),
                threshold_value=Decimal(str(limit["threshold_value"])),
                unit=str(limit["unit"]),
                scope=str(limit["scope"]),
                severity=str(limit["severity"]),
                direction=str(limit["direction"]),
                description=str(limit["description"]),
            )
            for limit in DEFAULT_POLICY_LIMITS
        ],
    )


def _snapshot_response(
    state: PortfolioRiskState,
    market_stats: PortfolioMarketStats,
    *,
    risk_level: str,
) -> RiskSnapshotResponse:
    top_weights = sorted(
        [_weight_pct(position.market_value, state.nav) for position in state.positions],
        reverse=True,
    )
    return RiskSnapshotResponse(
        portfolio_id=state.portfolio_id,
        portfolio_name=state.portfolio_name,
        calculated_at=state.calculated_at,
        as_of_date=state.as_of_date,
        nav=state.nav,
        cash_balance=state.cash_balance,
        invested_value=state.invested_value,
        cash_pct=_weight_pct(state.cash_balance, state.nav),
        gross_exposure_pct=_weight_pct(
            sum(
                (position.exposure_value for position in state.positions), Decimal("0")
            ),
            state.nav,
        ),
        net_exposure_pct=_weight_pct(
            sum((position.market_value for position in state.positions), Decimal("0")),
            state.nav,
        ),
        top_position_pct=top_weights[0] if top_weights else Decimal("0.0000"),
        top5_concentration_pct=sum(top_weights[:5], Decimal("0")).quantize(
            Decimal("0.0001")
        ),
        portfolio_volatility_pct=market_stats.portfolio_volatility_pct,
        beta_to_benchmark=market_stats.beta_to_benchmark,
        max_drawdown_pct=market_stats.max_drawdown_pct,
        var_95_pct=market_stats.var_95_pct,
        expected_shortfall_95_pct=market_stats.expected_shortfall_95_pct,
        liquidity_days=market_stats.liquidity_days,
        risk_level=risk_level,
        risk_level_label=_risk_level_label(risk_level),
    )


def _position_responses(
    state: PortfolioRiskState,
    market_stats: PortfolioMarketStats,
) -> list[RiskPositionResponse]:
    stats_by_ticker = market_stats.position_stats or {}
    return [
        RiskPositionResponse(
            instrument_id=position.instrument_id,
            ticker=position.ticker,
            name=position.name,
            asset_class=position.asset_class,
            sector=position.sector,
            quantity=position.quantity,
            average_cost=position.average_cost,
            market_value=position.market_value,
            unrealized_pnl=position.unrealized_pnl,
            weight_pct=_weight_pct(position.market_value, state.nav),
            volatility_pct=stats_by_ticker.get(
                position.ticker, PositionMarketStats()
            ).volatility_pct,
            beta_to_benchmark=stats_by_ticker.get(
                position.ticker, PositionMarketStats()
            ).beta_to_benchmark,
            liquidity_days=stats_by_ticker.get(
                position.ticker, PositionMarketStats()
            ).liquidity_days,
        )
        for position in state.positions
    ]


def _exposure_buckets(
    positions: list[RiskPosition],
    nav: Decimal,
    *,
    key_fn,
) -> list[RiskExposureBucketResponse]:
    values: dict[str, Decimal] = {}
    for position in positions:
        key = str(key_fn(position))
        values[key] = values.get(key, Decimal("0")) + position.market_value
    return [
        RiskExposureBucketResponse(
            name=name,
            market_value=money(value),
            exposure_pct=_weight_pct(value, nav),
        )
        for name, value in sorted(
            values.items(), key=lambda item: item[1], reverse=True
        )
    ]


def _policy_metric_values(
    state: PortfolioRiskState,
    market_stats: PortfolioMarketStats,
    asset_class_exposure: list[RiskExposureBucketResponse],
    sector_exposure: list[RiskExposureBucketResponse],
) -> dict[str, Decimal | None]:
    top_weights = sorted(
        [_weight_pct(position.market_value, state.nav) for position in state.positions],
        reverse=True,
    )
    largest_equity = max(
        [
            _weight_pct(position.market_value, state.nav)
            for position in state.positions
            if position.asset_class == "equity"
        ],
        default=Decimal("0.0000"),
    )
    largest_etf = max(
        [
            _weight_pct(position.market_value, state.nav)
            for position in state.positions
            if position.asset_class == "etf"
        ],
        default=Decimal("0.0000"),
    )
    largest_sector = max(
        [bucket.exposure_pct for bucket in sector_exposure],
        default=Decimal("0.0000"),
    )
    gross_exposure = _weight_pct(
        sum((position.exposure_value for position in state.positions), Decimal("0")),
        state.nav,
    )
    return {
        "max_single_equity_position_pct": largest_equity,
        "max_etf_position_pct": largest_etf,
        "max_sector_exposure_pct": largest_sector,
        "min_cash_allocation_pct": _weight_pct(state.cash_balance, state.nav),
        "max_gross_exposure_pct": gross_exposure,
        "max_top5_concentration_pct": sum(top_weights[:5], Decimal("0")).quantize(
            Decimal("0.0001")
        ),
        "max_portfolio_volatility_pct": market_stats.portfolio_volatility_pct,
        "max_var_95_pct": market_stats.var_95_pct,
        "max_expected_shortfall_95_pct": market_stats.expected_shortfall_95_pct,
        "max_liquidity_days": market_stats.liquidity_days,
    }


def _limit_passed(
    value: Decimal | None,
    threshold: Decimal,
    direction: str,
) -> bool:
    if value is None:
        return True
    if direction == "gte":
        return value >= threshold
    if direction == "lte_abs":
        return abs(value) <= threshold
    return value <= threshold


def _limit_message(
    limit: dict,
    value: Decimal | None,
    threshold: Decimal,
    passed: bool,
) -> str:
    if value is None:
        return f"{limit['label']} cannot be measured yet."
    comparator = "above" if str(limit["direction"]).startswith("lte") else "below"
    if passed:
        return f"{limit['label']} is within policy at {value} {limit['unit']}."
    return f"{limit['label']} is {comparator} policy: {value} vs {threshold} {limit['unit']}."


def _returns_by_date(bars: list[MarketPriceBar]) -> dict[date, float]:
    sorted_bars = sorted(bars, key=lambda bar: bar.bar_date)
    returns = {}
    for previous, current in zip(sorted_bars, sorted_bars[1:]):
        start = previous.adjusted_close_price or previous.close_price
        end = current.adjusted_close_price or current.close_price
        if start == 0:
            continue
        returns[current.bar_date] = float((end - start) / start)
    return returns


def _portfolio_returns(
    weights: dict[str, float],
    returns_by_ticker: dict[str, dict[date, float]],
) -> dict[date, float]:
    if not weights:
        return {}
    common_dates = None
    for ticker in weights:
        ticker_dates = set(returns_by_ticker.get(ticker, {}))
        if not ticker_dates:
            continue
        common_dates = (
            ticker_dates if common_dates is None else common_dates & ticker_dates
        )
    if not common_dates:
        return {}
    return {
        item_date: sum(
            weights[ticker] * returns_by_ticker.get(ticker, {}).get(item_date, 0.0)
            for ticker in weights
        )
        for item_date in sorted(common_dates)
    }


def _align_series(
    first: dict[date, float],
    second: dict[date, float],
) -> tuple[list[float], list[float]]:
    common_dates = sorted(set(first) & set(second))
    return [first[item] for item in common_dates], [
        second[item] for item in common_dates
    ]


def _volatility_pct(returns: list[float]) -> Decimal | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
    return _decimal4(sqrt(variance) * sqrt(252) * 100)


def _beta_pct(series: list[float], benchmark: list[float]) -> Decimal | None:
    if len(series) < 3 or len(series) != len(benchmark):
        return None
    benchmark_mean = sum(benchmark) / len(benchmark)
    series_mean = sum(series) / len(series)
    variance = sum((item - benchmark_mean) ** 2 for item in benchmark)
    if variance == 0:
        return None
    covariance = sum(
        (series_item - series_mean) * (benchmark_item - benchmark_mean)
        for series_item, benchmark_item in zip(series, benchmark)
    )
    return _decimal4(covariance / variance)


def _max_drawdown_from_fraction_returns(returns: list[float]) -> Decimal | None:
    if not returns:
        return None
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        if peak != 0:
            worst = min(worst, (equity - peak) / peak)
    return _decimal4(worst * 100)


def _var_pct(returns: list[float], percentile: int) -> Decimal | None:
    if len(returns) < 20:
        return None
    sorted_returns = sorted(returns)
    index = max(int(len(sorted_returns) * percentile / 100) - 1, 0)
    return _decimal4(sorted_returns[index] * 100)


def _expected_shortfall_pct(returns: list[float], percentile: int) -> Decimal | None:
    value_at_risk = _var_pct(returns, percentile)
    if value_at_risk is None:
        return None
    threshold = float(value_at_risk) / 100
    tail = [item for item in returns if item <= threshold]
    if not tail:
        return value_at_risk
    return _decimal4((sum(tail) / len(tail)) * 100)


def _liquidity_days(
    position: RiskPosition,
    bars: list[MarketPriceBar],
) -> Decimal | None:
    recent = [
        bar for bar in sorted(bars, key=lambda item: item.bar_date)[-20:] if bar.volume
    ]
    if not recent:
        return None
    dollar_volumes = []
    for bar in recent:
        price = bar.adjusted_close_price or bar.close_price
        dollar_volumes.append(price * Decimal(bar.volume or 0))
    average_dollar_volume = sum(dollar_volumes, Decimal("0")) / Decimal(
        len(dollar_volumes)
    )
    if average_dollar_volume <= 0:
        return None
    daily_capacity = average_dollar_volume * Decimal("0.10")
    return _decimal4(float(abs(position.market_value) / daily_capacity))


def _correlation_pairs(
    returns_by_ticker: dict[str, dict[date, float]],
    positions: list[RiskPosition],
) -> list[CorrelationPairResponse]:
    tickers = [position.ticker for position in positions]
    pairs: list[CorrelationPairResponse] = []
    for index, ticker_a in enumerate(tickers):
        for ticker_b in tickers[index + 1 :]:
            series_a, series_b = _align_series(
                returns_by_ticker.get(ticker_a, {}),
                returns_by_ticker.get(ticker_b, {}),
            )
            correlation = _correlation(series_a, series_b)
            if correlation is None:
                continue
            pairs.append(
                CorrelationPairResponse(
                    ticker_a=ticker_a,
                    ticker_b=ticker_b,
                    correlation=correlation,
                )
            )
    return sorted(pairs, key=lambda item: abs(item.correlation), reverse=True)[:10]


def _correlation(first: list[float], second: list[float]) -> Decimal | None:
    if len(first) < 3 or len(first) != len(second):
        return None
    first_mean = sum(first) / len(first)
    second_mean = sum(second) / len(second)
    first_var = sum((item - first_mean) ** 2 for item in first)
    second_var = sum((item - second_mean) ** 2 for item in second)
    if first_var == 0 or second_var == 0:
        return None
    covariance = sum(
        (first_item - first_mean) * (second_item - second_mean)
        for first_item, second_item in zip(first, second)
    )
    return _decimal4(covariance / sqrt(first_var * second_var))


def _apply_trade_to_state(
    state: PortfolioRiskState,
    payload: PreTradeRiskCheckCreate,
) -> tuple[PortfolioRiskState, Decimal, list[str]]:
    ticker = payload.instrument.ticker.upper()
    trade_value = money(payload.quantity * payload.price)
    cash_impact = -(trade_value + payload.fees)
    if payload.side == "sell":
        cash_impact = trade_value - payload.fees

    messages: list[str] = []
    positions = list(state.positions)
    existing_index = next(
        (
            index
            for index, position in enumerate(positions)
            if position.ticker == ticker
        ),
        None,
    )
    if existing_index is None:
        if payload.side == "sell":
            messages.append("Sell order has no existing long position.")
        positions.append(
            RiskPosition(
                instrument_id=None,
                ticker=ticker,
                name=payload.instrument.name,
                asset_class=payload.instrument.asset_class,
                sector=payload.instrument.sector,
                quantity=payload.quantity if payload.side == "buy" else Decimal("0"),
                average_cost=payload.price,
                market_value=(
                    money(payload.quantity * payload.price)
                    if payload.side == "buy"
                    else Decimal("0")
                ),
                unrealized_pnl=Decimal("0"),
            )
        )
    else:
        existing = positions[existing_index]
        quantity = (
            existing.quantity + payload.quantity
            if payload.side == "buy"
            else existing.quantity - payload.quantity
        )
        if quantity < 0:
            messages.append("Sell quantity exceeds the current position.")
            quantity = Decimal("0")
        market_value = money(quantity * payload.price)
        positions[existing_index] = RiskPosition(
            instrument_id=existing.instrument_id,
            ticker=existing.ticker,
            name=existing.name,
            asset_class=existing.asset_class,
            sector=existing.sector,
            quantity=quantity,
            average_cost=existing.average_cost,
            market_value=market_value,
            unrealized_pnl=money((payload.price - existing.average_cost) * quantity),
        )

    positions = [position for position in positions if position.quantity > 0]
    cash_balance = money(state.cash_balance + cash_impact)
    invested_value = money(
        sum((position.market_value for position in positions), Decimal("0"))
    )
    nav = money(cash_balance + invested_value)
    if nav <= 0:
        nav = Decimal("1.00")
    return (
        PortfolioRiskState(
            portfolio_id=state.portfolio_id,
            portfolio_name=state.portfolio_name,
            calculated_at=datetime.now(timezone.utc),
            as_of_date=payload.trade_date.date(),
            nav=nav,
            cash_balance=cash_balance,
            invested_value=invested_value,
            positions=positions,
        ),
        cash_impact,
        messages,
    )


def _pre_trade_decision(
    risk_level: str,
    failed_checks: list[RiskMeasurementResponse],
    messages: list[str],
) -> str:
    if any(
        "exceeds the current position" in message
        or "no existing long position" in message
        for message in messages
    ):
        return "reject"
    if risk_level == "halt":
        return "reject"
    if risk_level in {"reduce", "suspend", "defensive"}:
        return "reduce_or_review"
    if failed_checks:
        return "review"
    return "approve"


def _custom_scenario_from_payload(payload: StressScenarioCreate) -> dict:
    return {
        "name": payload.name,
        "scenario_type": "custom",
        "market_shock_pct": payload.market_shock_pct,
        "sector_shocks_pct": {
            key: value for key, value in payload.sector_shocks_pct.items()
        },
        "ticker_shocks_pct": {
            key.upper(): value for key, value in payload.ticker_shocks_pct.items()
        },
        "cash_shock_pct": payload.cash_shock_pct,
        "notes": [payload.notes] if payload.notes else [],
    }


def _position_shock(position: RiskPosition, scenario: dict) -> Decimal:
    shock = _decimal(scenario.get("market_shock_pct"))
    sector_shocks = scenario.get("sector_shocks_pct") or {}
    ticker_shocks = scenario.get("ticker_shocks_pct") or {}
    if position.sector and position.sector in sector_shocks:
        shock += _decimal(sector_shocks[position.sector])
    if position.ticker in ticker_shocks:
        shock += _decimal(ticker_shocks[position.ticker])
    return shock


def _largest_sector(state: PortfolioRiskState) -> str | None:
    values: dict[str, Decimal] = {}
    for position in state.positions:
        sector = position.sector or "Unclassified"
        values[sector] = values.get(sector, Decimal("0")) + position.market_value
    if not values:
        return None
    return max(values.items(), key=lambda item: item[1])[0]


def _stress_severity(nav_impact_pct: Decimal) -> str:
    loss = abs(nav_impact_pct) if nav_impact_pct < 0 else Decimal("0")
    if loss >= Decimal("20"):
        return "halt"
    if loss >= Decimal("10"):
        return "reduce"
    if loss >= Decimal("5"):
        return "warning"
    return "info"


def _risk_level_label(risk_level: str) -> str:
    labels = {
        "normal": "Normal",
        "warning": "Warning",
        "reduce": "Reduce risk",
        "suspend": "Suspend strategy",
        "defensive": "Defensive mode",
        "halt": "Trading halt",
    }
    return labels.get(risk_level, risk_level.title())


def _weight_pct(value: Decimal, nav: Decimal) -> Decimal:
    if nav == 0:
        return Decimal("0.0000")
    return ((value / nav) * Decimal("100")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def _decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal4(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _json_payload(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_payload(item) for item in value]
    return value
