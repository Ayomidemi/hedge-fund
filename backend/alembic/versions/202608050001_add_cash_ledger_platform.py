"""Add platform to cash ledger entries."""

from alembic import op
import sqlalchemy as sa


revision = "202608050001"
down_revision = "202608030001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cash_ledger_entries",
        sa.Column("platform", sa.String(length=64), nullable=False, server_default="manual"),
    )
    op.alter_column("cash_ledger_entries", "platform", server_default=None)


def downgrade() -> None:
    op.drop_column("cash_ledger_entries", "platform")
