"""Persist fair history preparation independent of radar priority."""
from alembic import op
import sqlalchemy as sa

revision = "202610140001"
down_revision = "202610070001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "radar_history_preparation",
        sa.Column("ticker", sa.String(32), primary_key=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("bar_count", sa.Integer(), nullable=False),
        sa.Column("last_bar_date", sa.Date()),
        sa.Column("last_error", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_radar_history_due", "radar_history_preparation", ["next_attempt_at", "last_attempt_at"])


def downgrade():
    op.drop_table("radar_history_preparation")
