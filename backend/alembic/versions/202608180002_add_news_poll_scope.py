"""add news poll scope

Revision ID: 202608180002
Revises: 202608180001
Create Date: 2026-08-18 17:15:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608180002"
down_revision: str | None = "202608180001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "news_poll_runs",
        sa.Column("target_scope", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "news_poll_runs",
        sa.Column("target_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "news_poll_runs",
        sa.Column(
            "cache_hit",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "news_poll_runs",
        sa.Column(
            "provider_plan",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_news_poll_runs_target_scope", "news_poll_runs", ["target_scope"]
    )
    op.create_index("ix_news_poll_runs_target_key", "news_poll_runs", ["target_key"])
    op.create_index(
        "ix_news_poll_runs_target_started",
        "news_poll_runs",
        ["target_scope", "target_key", "status", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_news_poll_runs_target_started", table_name="news_poll_runs")
    op.drop_index("ix_news_poll_runs_target_key", table_name="news_poll_runs")
    op.drop_index("ix_news_poll_runs_target_scope", table_name="news_poll_runs")
    op.drop_column("news_poll_runs", "provider_plan")
    op.drop_column("news_poll_runs", "cache_hit")
    op.drop_column("news_poll_runs", "target_key")
    op.drop_column("news_poll_runs", "target_scope")
