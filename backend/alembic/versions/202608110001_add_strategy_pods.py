"""add strategy pods

Revision ID: 202608110001
Revises: 202608100001
Create Date: 2026-08-11 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608110001"
down_revision: str | None = "202608100001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_pods",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("mandate", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_stage", sa.String(length=64), nullable=False),
        sa.Column("capital_allocation_pct", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("risk_budget_pct", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("volatility_target_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("max_drawdown_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("turnover_ceiling_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("approved_instruments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evaluation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("shutdown_criteria", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_strategy_pods_code"), "strategy_pods", ["code"], unique=False)

    op.create_table(
        "strategy_pod_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("strategy_pod_id", sa.UUID(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_stage", sa.String(length=64), nullable=False),
        sa.Column("capital_allocation_pct", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("risk_budget_pct", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("current_signal_score", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("model_confidence", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("allocation_recommendation", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["strategy_pod_id"], ["strategy_pods.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_strategy_pod_snapshots_as_of_date"), "strategy_pod_snapshots", ["as_of_date"], unique=False)
    op.create_index(op.f("ix_strategy_pod_snapshots_strategy_pod_id"), "strategy_pod_snapshots", ["strategy_pod_id"], unique=False)
    op.create_index(
        "ix_strategy_pod_snapshots_pod_captured",
        "strategy_pod_snapshots",
        ["strategy_pod_id", "captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_pod_snapshots_pod_captured", table_name="strategy_pod_snapshots")
    op.drop_index(op.f("ix_strategy_pod_snapshots_strategy_pod_id"), table_name="strategy_pod_snapshots")
    op.drop_index(op.f("ix_strategy_pod_snapshots_as_of_date"), table_name="strategy_pod_snapshots")
    op.drop_table("strategy_pod_snapshots")
    op.drop_index(op.f("ix_strategy_pods_code"), table_name="strategy_pods")
    op.drop_table("strategy_pods")
