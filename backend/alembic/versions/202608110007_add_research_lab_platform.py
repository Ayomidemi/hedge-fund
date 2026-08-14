"""add research lab platform

Revision ID: 202608110007
Revises: 202608110006
Create Date: 2026-08-11 18:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608110007"
down_revision: str | None = "202608110006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="completed",
        ),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("rebalance_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cumulative_return_pct",
            sa.Numeric(12, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("benchmark_return_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column("alpha_pct", sa.Numeric(12, 4), nullable=True),
        sa.Column(
            "annualized_return_pct",
            sa.Numeric(12, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "annualized_volatility_pct",
            sa.Numeric(12, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("sharpe_ratio", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column(
            "max_drawdown_pct", sa.Numeric(12, 4), nullable=False, server_default="0"
        ),
        sa.Column("hit_rate_pct", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("turnover_pct", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("cost_drag_pct", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column(
            "regime_filter_applied",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("skipped_by_regime", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "periods",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtest_runs_owner_user_id", "backtest_runs", ["owner_user_id"]
    )
    op.create_index(
        "ix_backtest_runs_owner_created",
        "backtest_runs",
        ["owner_user_id", "created_at"],
    )

    op.create_table(
        "research_experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("experiment_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="completed",
        ),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("primary_metric", sa.String(length=128), nullable=True),
        sa.Column("primary_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("backtest_run_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
        sa.ForeignKeyConstraint(["backtest_run_id"], ["backtest_runs.id"]),
    )
    op.create_index(
        "ix_research_experiments_owner_user_id",
        "research_experiments",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_research_experiments_owner_created",
        "research_experiments",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        "ix_research_experiments_model_version_id",
        "research_experiments",
        ["model_version_id"],
    )
    op.create_index(
        "ix_research_experiments_backtest_run_id",
        "research_experiments",
        ["backtest_run_id"],
    )

    op.create_table(
        "research_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["experiment_id"], ["research_experiments.id"]),
    )
    op.create_index(
        "ix_research_notes_owner_user_id", "research_notes", ["owner_user_id"]
    )
    op.create_index(
        "ix_research_notes_owner_created",
        "research_notes",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        "ix_research_notes_experiment_id", "research_notes", ["experiment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_research_notes_experiment_id", table_name="research_notes")
    op.drop_index("ix_research_notes_owner_created", table_name="research_notes")
    op.drop_index("ix_research_notes_owner_user_id", table_name="research_notes")
    op.drop_table("research_notes")
    op.drop_index(
        "ix_research_experiments_backtest_run_id", table_name="research_experiments"
    )
    op.drop_index(
        "ix_research_experiments_model_version_id", table_name="research_experiments"
    )
    op.drop_index(
        "ix_research_experiments_owner_created", table_name="research_experiments"
    )
    op.drop_index(
        "ix_research_experiments_owner_user_id", table_name="research_experiments"
    )
    op.drop_table("research_experiments")
    op.drop_index("ix_backtest_runs_owner_created", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_owner_user_id", table_name="backtest_runs")
    op.drop_table("backtest_runs")
