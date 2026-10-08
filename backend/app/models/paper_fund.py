"""Automatic execution plans for the Capital ledger. No live broker orders."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class PaperFundRun(Base, TimestampMixin):
    __tablename__ = "paper_fund_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("portfolios.id"), index=True)
    net_contributions_at_start: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    start_key: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    high_water_equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    max_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    halt_reason: Mapped[str | None] = mapped_column(Text)
    policy: Mapped[dict] = mapped_column(JSONB, nullable=False)
    risk_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    blockers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        Index("uq_paper_fund_start_key", "owner_user_id", "start_key", unique=True),
        CheckConstraint("starting_cash > 0 AND cash_balance >= 0", name="ck_paper_fund_capital"),
        CheckConstraint("status IN ('running','paused','liquidating','completed','halted')", name="ck_paper_fund_status"),
        Index("uq_paper_fund_active_owner", "owner_user_id", unique=True,
              postgresql_where=text("status <> 'completed'")),
    )


class PaperOrder(Base, TimestampMixin):
    """One long position lifecycle, including its limit entry and OCO exits."""

    __tablename__ = "paper_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_fund_runs.id"), nullable=False, index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    stop_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    mark_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    entry_fee: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    exit_fee: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_quote_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_quote_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mark_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_reason: Mapped[str | None] = mapped_column(String(255))
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index("uq_paper_order_run_instrument", "run_id", "instrument_id", unique=True),
        CheckConstraint("quantity > 0 AND stop_price > 0 AND stop_price < limit_price AND target_price > limit_price", name="ck_paper_order_plan"),
        CheckConstraint("status IN ('pending','open','closed','cancelled','expired')", name="ck_paper_order_status"),
    )


class PaperEquitySnapshot(Base):
    __tablename__ = "paper_equity_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_fund_runs.id"), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)

    __table_args__ = (Index("ix_paper_equity_run_time", "run_id", "recorded_at"),)
