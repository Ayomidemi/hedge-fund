"""add instrument quotes and price refresh runs

Revision ID: 202608110005
Revises: 202608110004
Create Date: 2026-08-11 11:55:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608110005"
down_revision: str | None = "202608110004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument_quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("previous_close", sa.Numeric(18, 6), nullable=True),
        sa.Column("change_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("day_open", sa.Numeric(18, 6), nullable=True),
        sa.Column("day_high", sa.Numeric(18, 6), nullable=True),
        sa.Column("day_low", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id"),
    )
    op.create_index(
        "ix_instrument_quotes_instrument_id",
        "instrument_quotes",
        ["instrument_id"],
        unique=False,
    )

    op.create_table(
        "price_refresh_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="running",
        ),
        sa.Column(
            "ticker_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "success_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "failure_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "positions_marked", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "interval_seconds", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "errors",
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
        "ix_price_refresh_runs_started_at",
        "price_refresh_runs",
        ["started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_price_refresh_runs_started_at", table_name="price_refresh_runs")
    op.drop_table("price_refresh_runs")
    op.drop_index("ix_instrument_quotes_instrument_id", table_name="instrument_quotes")
    op.drop_table("instrument_quotes")
