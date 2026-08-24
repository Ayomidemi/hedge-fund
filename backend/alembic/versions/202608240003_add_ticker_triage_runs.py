"""Add persisted ticker triage runs.

Revision ID: 202608240003
Revises: 202608240002
Create Date: 2026-08-24 19:15:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608240003"
down_revision: str | None = "202608240002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticker_triage_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market", sa.String(length=16), nullable=False),
        sa.Column("research_priority", sa.String(length=32), nullable=False),
        sa.Column("initial_view", sa.String(length=32), nullable=False),
        sa.Column("triage_decision", sa.String(length=32), nullable=False),
        sa.Column("action_label", sa.String(length=64), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("conviction_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("composite_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("recommended_weight", sa.Numeric(8, 4), nullable=False),
        sa.Column("top_drivers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("top_blockers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("why_now", sa.Text(), nullable=False),
        sa.Column("next_action", sa.Text(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_reference", sa.String(length=512), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scorecard", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticker_triage_runs_owner_user_id",
        "ticker_triage_runs",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_ticker_triage_runs_instrument_id",
        "ticker_triage_runs",
        ["instrument_id"],
    )
    op.create_index(
        "ix_ticker_triage_owner_instrument_generated",
        "ticker_triage_runs",
        ["owner_user_id", "instrument_id", "generated_at"],
    )
    op.create_index(
        "ix_ticker_triage_owner_generated",
        "ticker_triage_runs",
        ["owner_user_id", "generated_at"],
    )
    op.create_index(
        "ix_ticker_triage_decision",
        "ticker_triage_runs",
        ["triage_decision"],
    )


def downgrade() -> None:
    op.drop_index("ix_ticker_triage_decision", table_name="ticker_triage_runs")
    op.drop_index("ix_ticker_triage_owner_generated", table_name="ticker_triage_runs")
    op.drop_index(
        "ix_ticker_triage_owner_instrument_generated",
        table_name="ticker_triage_runs",
    )
    op.drop_index("ix_ticker_triage_runs_instrument_id", table_name="ticker_triage_runs")
    op.drop_index("ix_ticker_triage_runs_owner_user_id", table_name="ticker_triage_runs")
    op.drop_table("ticker_triage_runs")
