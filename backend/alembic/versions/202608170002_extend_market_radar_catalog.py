"""extend market radar catalog

Revision ID: 202608170002
Revises: 202608170001
Create Date: 2026-08-17 17:15:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608170002"
down_revision: str | None = "202608170001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radar_universe_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("source_rank", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "always_watched",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("liquidity_rank", sa.Integer(), nullable=True),
        sa.Column("avg_dollar_volume", sa.Numeric(24, 4), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("ticker", name="uq_radar_universe_members_ticker"),
    )
    op.create_index(
        "ix_radar_universe_members_ticker",
        "radar_universe_members",
        ["ticker"],
    )
    op.create_index(
        "ix_radar_universe_active_jurisdiction",
        "radar_universe_members",
        ["is_active", "jurisdiction"],
    )
    op.create_index(
        "ix_radar_universe_industry",
        "radar_universe_members",
        ["jurisdiction", "sector", "industry"],
    )

    op.add_column(
        "radar_runs",
        sa.Column("triggered_by_user_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "radar_runs",
        sa.Column("cache_hits", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "radar_runs",
        sa.Column("catalog_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "radar_runs",
        sa.Column(
            "promotion_owner_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index(
        "ix_radar_runs_triggered_by_user_id",
        "radar_runs",
        ["triggered_by_user_id"],
    )

    op.add_column(
        "radar_snapshots",
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "radar_snapshots",
        sa.Column(
            "sparkline",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "radar_snapshots",
        sa.Column("source_as_of", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "radar_snapshots",
        sa.Column(
            "carried_forward",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "radar_snapshots",
        sa.Column("stale_reason", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("radar_snapshots", "stale_reason")
    op.drop_column("radar_snapshots", "carried_forward")
    op.drop_column("radar_snapshots", "source_as_of")
    op.drop_column("radar_snapshots", "sparkline")
    op.drop_column("radar_snapshots", "evidence")

    op.drop_index("ix_radar_runs_triggered_by_user_id", table_name="radar_runs")
    op.drop_column("radar_runs", "promotion_owner_ids")
    op.drop_column("radar_runs", "catalog_count")
    op.drop_column("radar_runs", "cache_hits")
    op.drop_column("radar_runs", "triggered_by_user_id")

    op.drop_index("ix_radar_universe_industry", table_name="radar_universe_members")
    op.drop_index(
        "ix_radar_universe_active_jurisdiction", table_name="radar_universe_members"
    )
    op.drop_index(
        "ix_radar_universe_members_ticker", table_name="radar_universe_members"
    )
    op.drop_table("radar_universe_members")
