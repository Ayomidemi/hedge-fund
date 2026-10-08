"""Persist Capital risk preference and execution circuit-breaker state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "202610070001"
down_revision = "202610050002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("portfolios", sa.Column("risk_profile", sa.String(16), nullable=False, server_default="medium"))
    op.create_check_constraint("ck_portfolio_risk_profile", "portfolios", "risk_profile IN ('low','medium','high')")
    op.add_column("paper_fund_runs", sa.Column("risk_state", postgresql.JSONB(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("paper_fund_runs", "risk_state")
    op.drop_constraint("ck_portfolio_risk_profile", "portfolios", type_="check")
    op.drop_column("portfolios", "risk_profile")
