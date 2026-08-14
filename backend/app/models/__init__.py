import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AssetClass(str, enum.Enum):
    EQUITY = "equity"
    ETF = "etf"
    BOND = "bond"
    COMMODITY = "commodity"
    CASH_EQUIVALENT = "cash_equivalent"
    OTHER = "other"


class TradeSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class TradeStatus(str, enum.Enum):
    PLANNED = "planned"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class RecommendationAction(str, enum.Enum):
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    WATCH = "watch"
    AVOID = "avoid"


class DecisionOutcome(str, enum.Enum):
    ACCEPTED = "accepted"
    OVERRIDDEN = "overridden"
    DEFERRED = "deferred"
    REJECTED = "rejected"


class EvidenceSourceType(str, enum.Enum):
    MARKET_DATA = "market_data"
    FUNDAMENTAL_DATA = "fundamental_data"
    FILING = "filing"
    NEWS = "news"
    MODEL_OUTPUT = "model_output"
    MANUAL_RESEARCH = "manual_research"
    OTHER = "other"


class RiskSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    REDUCE = "reduce"
    SUSPEND = "suspend"
    HALT = "halt"


class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    sector: Mapped[str | None] = mapped_column(String(128))
    industry: Mapped[str | None] = mapped_column(String(128))

    positions: Mapped[list["Position"]] = relationship(back_populates="instrument")
    trades: Mapped[list["Trade"]] = relationship(back_populates="instrument")
    recommendations: Mapped[list["ModelRecommendation"]] = relationship(
        back_populates="instrument"
    )
    ticker_memos: Mapped[list["TickerMemo"]] = relationship(back_populates="instrument")
    market_price_bars: Mapped[list["MarketPriceBar"]] = relationship(
        back_populates="instrument"
    )
    feature_snapshots: Mapped[list["TickerFeatureSnapshot"]] = relationship(
        back_populates="instrument"
    )
    training_labels: Mapped[list["TickerTrainingLabel"]] = relationship(
        back_populates="instrument",
        foreign_keys="TickerTrainingLabel.instrument_id",
    )
    quote: Mapped["InstrumentQuote | None"] = relationship(
        back_populates="instrument", uselist=False
    )


class Portfolio(Base, TimestampMixin):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    mandate: Mapped[str | None] = mapped_column(Text)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    cash_entries: Mapped[list["CashLedgerEntry"]] = relationship(
        back_populates="portfolio"
    )
    positions: Mapped[list["Position"]] = relationship(back_populates="portfolio")
    trades: Mapped[list["Trade"]] = relationship(back_populates="portfolio")
    risk_limits: Mapped[list["RiskLimit"]] = relationship(back_populates="portfolio")
    risk_snapshots: Mapped[list["PortfolioRiskSnapshot"]] = relationship(
        back_populates="portfolio"
    )

    __table_args__ = (
        Index("ix_portfolios_owner_user_id_unique", "owner_user_id", unique=True),
        Index("ix_portfolios_owner_name", "owner_user_id", "name", unique=True),
    )


class CashLedgerEntry(Base, TimestampMixin):
    __tablename__ = "cash_ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), nullable=False, index=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    description: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(String(255))

    portfolio: Mapped["Portfolio"] = relationship(back_populates="cash_entries")


class Position(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")
    instrument: Mapped["Instrument"] = relationship(back_populates="positions")


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    pod: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    training_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    assumptions: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    approved_use: Mapped[str | None] = mapped_column(Text)
    prohibited_use: Mapped[str | None] = mapped_column(Text)
    shutdown_criteria: Mapped[str | None] = mapped_column(Text)

    recommendations: Mapped[list["ModelRecommendation"]] = relationship(
        back_populates="model_version"
    )

    __table_args__ = (
        Index("ix_model_versions_name_version", "name", "version", unique=True),
    )


class ModelRecommendation(Base, TimestampMixin):
    __tablename__ = "model_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id"), nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    conviction_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    recommended_weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    time_horizon: Mapped[str | None] = mapped_column(String(64))
    thesis: Mapped[str | None] = mapped_column(Text)
    scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_summary: Mapped[str | None] = mapped_column(Text)

    model_version: Mapped["ModelVersion"] = relationship(
        back_populates="recommendations"
    )
    instrument: Mapped["Instrument"] = relationship(back_populates="recommendations")
    decisions: Mapped[list["HumanModelDecision"]] = relationship(
        back_populates="recommendation"
    )
    evidence_snapshots: Mapped[list["EvidenceSnapshot"]] = relationship(
        back_populates="recommendation"
    )


class Trade(Base, TimestampMixin):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_recommendations.id"), index=True
    )
    trade_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TradeStatus.PLANNED.value
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    executed_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    risk_notes: Mapped[str | None] = mapped_column(Text)
    broker_reference: Mapped[str | None] = mapped_column(String(255))

    portfolio: Mapped["Portfolio"] = relationship(back_populates="trades")
    instrument: Mapped["Instrument"] = relationship(back_populates="trades")


class RiskLimit(Base, TimestampMixin):
    __tablename__ = "risk_limits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    limit_type: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RiskSeverity.WARNING.value
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    portfolio: Mapped["Portfolio | None"] = relationship(back_populates="risk_limits")
    risk_checks: Mapped[list["RiskCheck"]] = relationship(back_populates="risk_limit")


class RiskCheck(Base, TimestampMixin):
    __tablename__ = "risk_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    risk_limit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_limits.id"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id"), index=True
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_recommendations.id"), index=True
    )
    trade_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trades.id"), index=True
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    observed_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False)
    message: Mapped[str | None] = mapped_column(Text)

    risk_limit: Mapped["RiskLimit"] = relationship(back_populates="risk_checks")


class StrategyPod(Base, TimestampMixin):
    __tablename__ = "strategy_pods"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    mandate: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="research")
    lifecycle_stage: Mapped[str] = mapped_column(
        String(64), nullable=False, default="research"
    )
    capital_allocation_pct: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0
    )
    risk_budget_pct: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=0
    )
    volatility_target_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    turnover_ceiling_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    approved_instruments: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    current_signals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evaluation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    shutdown_criteria: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    snapshots: Mapped[list["StrategyPodSnapshot"]] = relationship(
        back_populates="strategy_pod"
    )

    __table_args__ = (
        Index("ix_strategy_pods_owner_code", "owner_user_id", "code", unique=True),
    )


class StrategyPodSnapshot(Base, TimestampMixin):
    __tablename__ = "strategy_pod_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_pod_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_pods.id"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    capital_allocation_pct: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False
    )
    risk_budget_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    current_signal_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    model_confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    allocation_recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    strategy_pod: Mapped["StrategyPod"] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index(
            "ix_strategy_pod_snapshots_pod_captured", "strategy_pod_id", "captured_at"
        ),
    )


class RiskPolicyVersion(Base, TimestampMixin):
    __tablename__ = "risk_policy_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    hierarchy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_risk_policy_versions_name_version", "name", "version", unique=True),
    )


class PortfolioRiskSnapshot(Base, TimestampMixin):
    __tablename__ = "portfolio_risk_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), nullable=False, index=True
    )
    risk_policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_policy_versions.id"), index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    nav: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    invested_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    gross_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    net_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    cash_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    top_position_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    top5_concentration_pct: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    portfolio_volatility_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    beta_to_benchmark: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    var_95_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    expected_shortfall_95_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    liquidity_days: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    exposures: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="risk_snapshots")

    __table_args__ = (
        Index(
            "ix_portfolio_risk_snapshots_portfolio_captured",
            "portfolio_id",
            "captured_at",
        ),
    )


class PositionRiskSnapshot(Base, TimestampMixin):
    __tablename__ = "position_risk_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_risk_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolio_risk_snapshots.id"), nullable=False, index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    weight_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    volatility_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    beta_to_benchmark: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    liquidity_days: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index(
            "ix_position_risk_snapshots_snapshot_ticker",
            "portfolio_risk_snapshot_id",
            "ticker",
        ),
    )


class RiskMeasurement(Base, TimestampMixin):
    __tablename__ = "risk_measurements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), nullable=False, index=True
    )
    portfolio_risk_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolio_risk_snapshots.id"), index=True
    )
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    measurement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    passed: Mapped[bool] = mapped_column(nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_risk_measurements_portfolio_measured", "portfolio_id", "measured_at"),
    )


class StressScenario(Base, TimestampMixin):
    __tablename__ = "stress_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scenario_type: Mapped[str] = mapped_column(String(64), nullable=False)
    shocks: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_system: Mapped[bool] = mapped_column(nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class StressTestResult(Base, TimestampMixin):
    __tablename__ = "stress_test_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id"), nullable=False, index=True
    )
    portfolio_risk_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolio_risk_snapshots.id"), index=True
    )
    stress_scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stress_scenarios.id"), index=True
    )
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scenario_name: Mapped[str] = mapped_column(String(128), nullable=False)
    nav_before: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    nav_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    nav_impact_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    worst_positions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_stress_test_results_portfolio_run", "portfolio_id", "run_at"),
    )


class EvidenceSnapshot(Base, TimestampMixin):
    __tablename__ = "evidence_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_recommendations.id"), index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(512))
    as_of_date: Mapped[date | None] = mapped_column(Date)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    data_version: Mapped[str | None] = mapped_column(String(128))

    recommendation: Mapped["ModelRecommendation | None"] = relationship(
        back_populates="evidence_snapshots"
    )


class TickerMemo(Base, TimestampMixin):
    __tablename__ = "ticker_memos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_recommendations.id"), index=True
    )
    memo_date: Mapped[date] = mapped_column(Date, nullable=False)
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    time_horizon: Mapped[str | None] = mapped_column(String(64))
    executive_view: Mapped[str] = mapped_column(Text, nullable=False)
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    bull_case: Mapped[str | None] = mapped_column(Text)
    base_case: Mapped[str | None] = mapped_column(Text)
    bear_case: Mapped[str | None] = mapped_column(Text)
    thesis_breakers: Mapped[str | None] = mapped_column(Text)
    risk_assessment: Mapped[str | None] = mapped_column(Text)
    scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    data_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    model_version_label: Mapped[str | None] = mapped_column(String(128))

    instrument: Mapped["Instrument"] = relationship(back_populates="ticker_memos")


class Opportunity(Base, TimestampMixin):
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True
    )
    source_memo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ticker_memos.id"), index=True
    )
    source_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_recommendations.id"), index=True
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="discovered"
    )
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    research_question: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    time_horizon: Mapped[str | None] = mapped_column(String(64))
    conviction_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    expected_edge_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    target_weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    review_by: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    status_history: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    instrument: Mapped["Instrument"] = relationship()
    source_memo: Mapped["TickerMemo | None"] = relationship(
        foreign_keys=[source_memo_id]
    )
    source_recommendation: Mapped["ModelRecommendation | None"] = relationship(
        foreign_keys=[source_recommendation_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "source_memo_id",
            name="uq_opportunities_owner_source_memo",
        ),
        Index("ix_opportunities_owner_status", "owner_user_id", "status"),
        Index("ix_opportunities_owner_priority", "owner_user_id", "priority"),
    )


class HumanModelDecision(Base, TimestampMixin):
    __tablename__ = "human_model_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_recommendations.id"), nullable=False, index=True
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_action: Mapped[str | None] = mapped_column(String(32))
    selected_weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(128))
    outcome_notes: Mapped[str | None] = mapped_column(Text)

    recommendation: Mapped["ModelRecommendation"] = relationship(
        back_populates="decisions"
    )


class MarketPriceBar(Base, TimestampMixin):
    __tablename__ = "market_price_bars"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True
    )
    bar_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    open_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    adjusted_close_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    instrument: Mapped["Instrument"] = relationship(back_populates="market_price_bars")

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "bar_date",
            "source",
            name="uq_market_price_bars_instrument_date_source",
        ),
        Index("ix_market_price_bars_instrument_date", "instrument_id", "bar_date"),
    )


class TickerFeatureSnapshot(Base, TimestampMixin):
    __tablename__ = "ticker_feature_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(512))
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    instrument: Mapped["Instrument"] = relationship(back_populates="feature_snapshots")

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "as_of_date",
            "feature_version",
            name="uq_ticker_feature_snapshots_instrument_date_version",
        ),
        Index(
            "ix_ticker_feature_snapshots_instrument_date", "instrument_id", "as_of_date"
        ),
    )


class TickerTrainingLabel(Base, TimestampMixin):
    __tablename__ = "ticker_training_labels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, index=True
    )
    benchmark_instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instruments.id"), index=True
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    forward_return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    benchmark_forward_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    relative_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    realized_volatility_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    label_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    instrument: Mapped["Instrument"] = relationship(
        back_populates="training_labels",
        foreign_keys=[instrument_id],
    )
    benchmark_instrument: Mapped["Instrument | None"] = relationship(
        foreign_keys=[benchmark_instrument_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "benchmark_instrument_id",
            "as_of_date",
            "horizon_days",
            "label_version",
            "source",
            name="uq_ticker_training_labels_identity",
        ),
        Index(
            "ix_ticker_training_labels_instrument_date", "instrument_id", "as_of_date"
        ),
    )


class InstrumentQuote(Base, TimestampMixin):
    """Latest live mark for an instrument. One row per instrument, updated in
    place on every price refresh cycle. All modules that display or mark
    prices read from this table instead of calling providers directly."""

    __tablename__ = "instrument_quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id"), nullable=False, unique=True, index=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    previous_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    day_open: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    day_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    day_low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_stale: Mapped[bool] = mapped_column(nullable=False, default=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    instrument: Mapped["Instrument"] = relationship(back_populates="quote")


class FxRate(Base, TimestampMixin):
    """Latest FX rate for a currency pair. Refreshed on the same schedule as
    instrument quotes. Rate is quote_currency per 1 base_currency
    (e.g. USD/NGN = 1363.18 means 1 USD = 1363.18 NGN)."""

    __tablename__ = "fx_rates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_stale: Mapped[bool] = mapped_column(nullable=False, default=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "base_currency",
            "quote_currency",
            name="uq_fx_rates_base_quote",
        ),
        Index("ix_fx_rates_base_quote", "base_currency", "quote_currency"),
    )


class PriceRefreshRun(Base, TimestampMixin):
    """Audit trail of price refresh cycles, surfaced in Administration."""

    __tablename__ = "price_refresh_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    ticker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positions_marked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        Index("ix_price_refresh_runs_started_at", "started_at"),
    )


class BacktestRun(Base, TimestampMixin):
    """Persisted walk-forward backtest run. Periods and parameters are stored
    so results are reproducible and comparable across research iterations."""

    __tablename__ = "backtest_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    rebalance_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cumulative_return_pct: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    benchmark_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    alpha_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    annualized_return_pct: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    annualized_volatility_pct: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    sharpe_ratio: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    max_drawdown_pct: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    hit_rate_pct: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    turnover_pct: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    cost_drag_pct: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    regime_filter_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    skipped_by_regime: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    periods: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        Index("ix_backtest_runs_owner_created", "owner_user_id", "created_at"),
    )


class ResearchExperiment(Base, TimestampMixin):
    """Tracked research trial. One row per pipeline run, training run, backtest,
    or regime fit so research history is auditable and comparable."""

    __tablename__ = "research_experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    experiment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    primary_metric: Mapped[str | None] = mapped_column(String(128))
    primary_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id"), index=True
    )
    backtest_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("backtest_runs.id"), index=True
    )

    __table_args__ = (
        Index("ix_research_experiments_owner_created", "owner_user_id", "created_at"),
    )


class ResearchNote(Base, TimestampMixin):
    """Lab notebook entry. Markdown research notes optionally linked to a
    tracked experiment."""

    __tablename__ = "research_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_experiments.id"), index=True
    )

    __table_args__ = (
        Index("ix_research_notes_owner_created", "owner_user_id", "created_at"),
    )


class SystemLogEntry(Base, TimestampMixin):
    __tablename__ = "system_log_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    event: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_system_log_entries_owner_created", "owner_user_id", "created_at"),
        Index("ix_system_log_entries_category_created", "category", "created_at"),
    )
