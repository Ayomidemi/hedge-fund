"""Link automatic execution to the existing Capital account.

No cash is created by this migration. Legacy execution records are attached
and their fills booked transactionally by the Capital integration service.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "202610050002"
down_revision = "202610050001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("portfolios", sa.Column("trading_mode", sa.String(16), nullable=False, server_default="manual"))
    op.create_check_constraint("ck_portfolio_trading_mode", "portfolios", "trading_mode IN ('manual','automatic')")
    op.add_column("paper_fund_runs", sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("paper_fund_runs", sa.Column("net_contributions_at_start", sa.Numeric(18, 2), nullable=True))
    op.create_foreign_key("fk_paper_run_portfolio", "paper_fund_runs", "portfolios", ["portfolio_id"], ["id"])
    op.create_index("ix_paper_fund_runs_portfolio_id", "paper_fund_runs", ["portfolio_id"])


def downgrade():
    op.drop_index("ix_paper_fund_runs_portfolio_id", table_name="paper_fund_runs")
    op.drop_constraint("fk_paper_run_portfolio", "paper_fund_runs", type_="foreignkey")
    op.drop_column("paper_fund_runs", "net_contributions_at_start")
    op.drop_column("paper_fund_runs", "portfolio_id")
    op.drop_constraint("ck_portfolio_trading_mode", "portfolios", type_="check")
    op.drop_column("portfolios", "trading_mode")
