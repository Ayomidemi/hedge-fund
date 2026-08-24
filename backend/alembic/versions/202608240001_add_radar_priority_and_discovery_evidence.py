"""Add radar priority fields and opportunity discovery evidence.

Revision ID: 202608240001
Revises: 202608180002
Create Date: 2026-08-24 14:45:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608240001"
down_revision: str | None = "202608180002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "radar_snapshots",
        sa.Column("radar_priority", sa.String(length=4), nullable=True),
    )
    op.add_column(
        "radar_snapshots",
        sa.Column(
            "priority_score",
            sa.Numeric(10, 4),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "radar_snapshots",
        sa.Column(
            "auto_promote",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_radar_snapshots_run_priority",
        "radar_snapshots",
        ["run_id", "radar_priority"],
    )
    op.add_column(
        "opportunities",
        sa.Column(
            "discovery_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("opportunities", "discovery_evidence")
    op.drop_index("ix_radar_snapshots_run_priority", table_name="radar_snapshots")
    op.drop_column("radar_snapshots", "auto_promote")
    op.drop_column("radar_snapshots", "priority_score")
    op.drop_column("radar_snapshots", "radar_priority")
