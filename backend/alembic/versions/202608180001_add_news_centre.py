"""add news centre

Revision ID: 202608180001
Revises: 202608170003
Create Date: 2026-08-18 10:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608180001"
down_revision: str | None = "202608170003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "news_poll_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("provider_calls", sa.Integer(), nullable=False),
        sa.Column("items_seen", sa.Integer(), nullable=False),
        sa.Column("items_created", sa.Integer(), nullable=False),
        sa.Column("items_updated", sa.Integer(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        "ix_news_poll_runs_started_at", "news_poll_runs", ["started_at"]
    )

    op.create_table(
        "news_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=512), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jurisdiction", sa.String(length=8), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("sentiment_label", sa.String(length=32), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.UniqueConstraint("provider", "provider_id", name="uq_news_items_provider_id"),
    )
    op.create_index("ix_news_items_published_at", "news_items", ["published_at"])
    op.create_index(
        "ix_news_items_provider_published", "news_items", ["provider", "published_at"]
    )

    op.create_table(
        "news_ticker_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("news_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("relevance_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("sentiment_label", sa.String(length=32), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(8, 4), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["news_item_id"], ["news_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "news_item_id", "ticker", name="uq_news_ticker_links_item_ticker"
        ),
    )
    op.create_index(
        "ix_news_ticker_links_instrument_id", "news_ticker_links", ["instrument_id"]
    )
    op.create_index(
        "ix_news_ticker_links_news_item_id", "news_ticker_links", ["news_item_id"]
    )
    op.create_index("ix_news_ticker_links_ticker", "news_ticker_links", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_news_ticker_links_ticker", table_name="news_ticker_links")
    op.drop_index("ix_news_ticker_links_news_item_id", table_name="news_ticker_links")
    op.drop_index("ix_news_ticker_links_instrument_id", table_name="news_ticker_links")
    op.drop_table("news_ticker_links")
    op.drop_index("ix_news_items_provider_published", table_name="news_items")
    op.drop_index("ix_news_items_published_at", table_name="news_items")
    op.drop_table("news_items")
    op.drop_index("ix_news_poll_runs_started_at", table_name="news_poll_runs")
    op.drop_table("news_poll_runs")
