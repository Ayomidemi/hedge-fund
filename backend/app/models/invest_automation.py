"""Automatic entry and exit plans for one Invest account.

Cash, positions and filled orders stay on the Invest ledger. This table is the
plan, not a second balance.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class InvestManagedOrder(Base, TimestampMixin):
    __tablename__ = "invest_managed_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invest_accounts.id"), nullable=False, index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    entry_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invest_orders.id"))
    exit_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invest_orders.id"))
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128))
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stop_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    mark_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    entry_fee: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    exit_fee: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    reserved_cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_quote_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_quote_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mark_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_reason: Mapped[str | None] = mapped_column(String(255))
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index(
            "uq_invest_managed_active",
            "account_id",
            "instrument_id",
            unique=True,
            postgresql_where=text("status IN ('pending','open')"),
        ),
        Index(
            "uq_invest_managed_signal",
            "account_id",
            "instrument_id",
            "signal_id",
            unique=True,
        ),
        CheckConstraint(
            "quantity > 0 AND stop_price > 0 AND stop_price < limit_price AND target_price > limit_price",
            name="ck_invest_managed_plan",
        ),
        CheckConstraint(
            "status IN ('pending','open','closed','cancelled','expired')",
            name="ck_invest_managed_status",
        ),
        CheckConstraint("reserved_cash >= 0", name="ck_invest_managed_reserved"),
    )
