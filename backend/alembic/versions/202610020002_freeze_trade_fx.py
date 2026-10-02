"""Persist base-currency execution costs instead of revaluing history.

Revision ID: 202610020002
Revises: 202610020001
"""
from alembic import op
import sqlalchemy as sa

revision = "202610020002"
down_revision = "202610020001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("trades", sa.Column("executed_price_base", sa.Numeric(18, 8)))
    op.add_column("trades", sa.Column("fees_base", sa.Numeric(18, 8)))
    # Native/base matches can be recovered exactly. Foreign fills require
    # historical FX provenance; do not fabricate a rate for those old rows.
    op.execute("""
        UPDATE trades AS t SET executed_price_base = t.executed_price, fees_base = t.fees
        FROM instruments AS i, portfolios AS p
        WHERE t.instrument_id = i.id AND t.portfolio_id = p.id
          AND i.currency = p.base_currency
    """)


def downgrade():
    op.drop_column("trades", "fees_base")
    op.drop_column("trades", "executed_price_base")
