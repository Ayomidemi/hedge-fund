"""Repair paper-fund schemas installed before start idempotency was added.

Revision ID: 202610050001
Revises: 202610020002

Some databases applied the original 202610020001 migration before its file
included start_key. A revision check alone cannot detect that missing column.
This forward repair supports both those databases and fresh installations.
"""
from alembic import op

revision = "202610050001"
down_revision = "202610020002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE paper_fund_runs ADD COLUMN IF NOT EXISTS start_key VARCHAR(128)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_fund_start_key "
        "ON paper_fund_runs (owner_user_id, start_key)"
    )


def downgrade():
    # The canonical preceding schema already contains this column and index.
    # Keep the repaired schema when moving back to that revision.
    pass
