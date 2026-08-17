"""add market radar

Revision ID: 202608170001
Revises: 202608110007
Create Date: 2026-08-17 15:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608170001"
down_revision: str | None = "202608110008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radar_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="running"
        ),
        sa.Column(
            "jurisdictions_requested",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "jurisdictions_scanned",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "jurisdictions_skipped",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("vendor_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "working_set_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("flagged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("promoted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "notes",
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
    op.create_index("ix_radar_runs_started_at", "radar_runs", ["started_at"])

    op.create_table(
        "radar_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column(
            "asset_class", sa.String(length=32), nullable=False, server_default="equity"
        ),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "always_watched", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "in_working_set", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("price", sa.Numeric(18, 6), nullable=True),
        sa.Column("previous_close", sa.Numeric(18, 6), nullable=True),
        sa.Column("change_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("avg_volume", sa.BigInteger(), nullable=True),
        sa.Column("volume_ratio", sa.Numeric(12, 4), nullable=True),
        sa.Column(
            "anomaly_score", sa.Numeric(10, 4), nullable=False, server_default="0"
        ),
        sa.Column(
            "flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["run_id"], ["radar_runs.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_radar_snapshots_run_id", "radar_snapshots", ["run_id"])
    op.create_index(
        "ix_radar_snapshots_run_score",
        "radar_snapshots",
        ["run_id", "anomaly_score"],
    )
    op.create_index(
        "ix_radar_snapshots_run_jurisdiction",
        "radar_snapshots",
        ["run_id", "jurisdiction"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_radar_snapshots_run_jurisdiction", table_name="radar_snapshots"
    )
    op.drop_index("ix_radar_snapshots_run_score", table_name="radar_snapshots")
    op.drop_index("ix_radar_snapshots_run_id", table_name="radar_snapshots")
    op.drop_table("radar_snapshots")
    op.drop_index("ix_radar_runs_started_at", table_name="radar_runs")
    op.drop_table("radar_runs")
