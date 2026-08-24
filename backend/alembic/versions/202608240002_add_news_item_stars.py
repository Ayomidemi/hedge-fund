"""Add user-saved news articles.

Revision ID: 202608240002
Revises: 202608240001
Create Date: 2026-08-24 18:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608240002"
down_revision: str | None = "202608240001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "news_item_stars",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("news_item_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["news_item_id"], ["news_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "news_item_id",
            name="uq_news_item_stars_owner_item",
        ),
    )
    op.create_index(
        "ix_news_item_stars_news_item_id",
        "news_item_stars",
        ["news_item_id"],
    )
    op.create_index(
        "ix_news_item_stars_owner_user_id",
        "news_item_stars",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_news_item_stars_owner_created",
        "news_item_stars",
        ["owner_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_news_item_stars_owner_created", table_name="news_item_stars")
    op.drop_index("ix_news_item_stars_owner_user_id", table_name="news_item_stars")
    op.drop_index("ix_news_item_stars_news_item_id", table_name="news_item_stars")
    op.drop_table("news_item_stars")
