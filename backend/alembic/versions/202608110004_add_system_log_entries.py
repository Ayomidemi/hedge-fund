"""add system log entries

Revision ID: 202608110004
Revises: 202608110003
Create Date: 2026-08-11 10:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608110004"
down_revision: str | None = "202608110003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_log_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("event", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "context",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_system_log_entries_owner_user_id",
        "system_log_entries",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_system_log_entries_owner_created",
        "system_log_entries",
        ["owner_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_system_log_entries_category_created",
        "system_log_entries",
        ["category", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_system_log_entries_category_created", table_name="system_log_entries")
    op.drop_index("ix_system_log_entries_owner_created", table_name="system_log_entries")
    op.drop_index("ix_system_log_entries_owner_user_id", table_name="system_log_entries")
    op.drop_table("system_log_entries")
