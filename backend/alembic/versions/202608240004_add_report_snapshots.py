"""Add persisted report snapshots.

Revision ID: 202608240004
Revises: 202608240003
Create Date: 2026-08-24 20:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608240004"
down_revision: str | None = "202608240003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_kind", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_label", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("nav", sa.Numeric(18, 4), nullable=True),
        sa.Column("return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_report_snapshots_owner_user_id",
        "report_snapshots",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_report_snapshots_portfolio_id",
        "report_snapshots",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_report_snapshots_period_start",
        "report_snapshots",
        ["period_start"],
    )
    op.create_index(
        "ix_report_snapshots_owner_kind_period",
        "report_snapshots",
        ["owner_user_id", "report_kind", "period_start"],
    )
    op.create_index(
        "ix_report_snapshots_owner_created",
        "report_snapshots",
        ["owner_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_report_snapshots_owner_created", table_name="report_snapshots")
    op.drop_index("ix_report_snapshots_owner_kind_period", table_name="report_snapshots")
    op.drop_index("ix_report_snapshots_period_start", table_name="report_snapshots")
    op.drop_index("ix_report_snapshots_portfolio_id", table_name="report_snapshots")
    op.drop_index("ix_report_snapshots_owner_user_id", table_name="report_snapshots")
    op.drop_table("report_snapshots")
