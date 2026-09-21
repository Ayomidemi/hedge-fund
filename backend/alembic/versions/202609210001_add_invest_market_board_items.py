"""add invest market board items

Revision ID: 202609210001
Revises: 202609150001
Create Date: 2026-09-21

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202609210001"
down_revision: str | None = "202609150001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invest_market_board_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("board_group", sa.String(length=64), nullable=False),
        sa.Column("group_title", sa.String(length=128), nullable=False),
        sa.Column("group_description", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column(
            "source",
            sa.String(length=64),
            nullable=False,
            server_default="board_rule",
        ),
        sa.Column("source_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        sa.UniqueConstraint("ticker", name="uq_invest_market_board_items_ticker"),
    )
    op.create_index(
        "ix_invest_market_board_items_ticker",
        "invest_market_board_items",
        ["ticker"],
    )
    op.create_index(
        "ix_invest_market_board_active_order",
        "invest_market_board_items",
        ["is_active", "market", "board_group", "display_order"],
    )


def downgrade() -> None:
    op.drop_table("invest_market_board_items")
