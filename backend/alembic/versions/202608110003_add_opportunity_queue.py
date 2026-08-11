"""add opportunity queue

Revision ID: 202608110003
Revises: 202608110002
Create Date: 2026-08-11 02:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608110003"
down_revision: str | None = "202608110002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_memo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "source_recommendation_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("research_question", sa.Text(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("time_horizon", sa.String(length=64), nullable=True),
        sa.Column("conviction_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("expected_edge_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("target_weight", sa.Numeric(8, 4), nullable=True),
        sa.Column("review_by", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status_history",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["source_memo_id"], ["ticker_memos.id"]),
        sa.ForeignKeyConstraint(
            ["source_recommendation_id"], ["model_recommendations.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "source_memo_id",
            name="uq_opportunities_owner_source_memo",
        ),
    )
    op.create_index(
        op.f("ix_opportunities_owner_user_id"),
        "opportunities",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opportunities_instrument_id"),
        "opportunities",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opportunities_source_memo_id"),
        "opportunities",
        ["source_memo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_opportunities_source_recommendation_id"),
        "opportunities",
        ["source_recommendation_id"],
        unique=False,
    )
    op.create_index(
        "ix_opportunities_owner_status",
        "opportunities",
        ["owner_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_opportunities_owner_priority",
        "opportunities",
        ["owner_user_id", "priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_opportunities_owner_priority", table_name="opportunities")
    op.drop_index("ix_opportunities_owner_status", table_name="opportunities")
    op.drop_index(
        op.f("ix_opportunities_source_recommendation_id"), table_name="opportunities"
    )
    op.drop_index(op.f("ix_opportunities_source_memo_id"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_instrument_id"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_owner_user_id"), table_name="opportunities")
    op.drop_table("opportunities")
