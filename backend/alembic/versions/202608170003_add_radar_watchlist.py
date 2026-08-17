"""add radar watchlist

Revision ID: 202608170003
Revises: 202608170002
Create Date: 2026-08-17 17:50:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608170003"
down_revision: str | None = "202608170002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radar_watchlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.UniqueConstraint(
            "owner_user_id", "ticker", name="uq_radar_watchlist_owner_ticker"
        ),
    )
    op.create_index(
        "ix_radar_watchlist_items_owner_user_id",
        "radar_watchlist_items",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_radar_watchlist_owner_added",
        "radar_watchlist_items",
        ["owner_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_radar_watchlist_owner_added", table_name="radar_watchlist_items")
    op.drop_index(
        "ix_radar_watchlist_items_owner_user_id", table_name="radar_watchlist_items"
    )
    op.drop_table("radar_watchlist_items")
