"""Resting Invest limits, share reserves, and a Capital short hedge."""
from alembic import op
import sqlalchemy as sa

revision = "202610190002"
down_revision = "202610190001"
branch_labels = None
depends_on = None

_PLAN = (
    "(direction = 'long' AND quantity > 0 AND stop_price > 0 AND stop_price < limit_price "
    "AND target_price > limit_price) OR (direction = 'short' AND quantity > 0 AND target_price > 0 "
    "AND target_price < limit_price AND stop_price > limit_price)"
)


def upgrade():
    op.add_column("invest_orders", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "invest_positions",
        sa.Column("reserved_quantity", sa.Numeric(24, 8), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_invest_position_reserved_quantity",
        "invest_positions",
        "reserved_quantity >= 0",
    )
    op.add_column(
        "paper_orders",
        sa.Column("direction", sa.String(8), nullable=False, server_default="long"),
    )
    op.drop_constraint("ck_paper_order_plan", "paper_orders", type_="check")
    op.create_check_constraint("ck_paper_order_plan", "paper_orders", _PLAN)
    op.add_column(
        "positions",
        sa.Column("exposure_side", sa.String(8), nullable=False, server_default="long"),
    )
    op.create_check_constraint(
        "ck_position_exposure_side",
        "positions",
        "exposure_side IN ('long', 'short')",
    )


def downgrade():
    op.drop_constraint("ck_position_exposure_side", "positions", type_="check")
    op.drop_column("positions", "exposure_side")
    op.drop_constraint("ck_paper_order_plan", "paper_orders", type_="check")
    op.create_check_constraint(
        "ck_paper_order_plan",
        "paper_orders",
        "quantity > 0 AND stop_price > 0 AND stop_price < limit_price AND target_price > limit_price",
    )
    op.drop_column("paper_orders", "direction")
    op.drop_constraint("ck_invest_position_reserved_quantity", "invest_positions", type_="check")
    op.drop_column("invest_positions", "reserved_quantity")
    op.drop_column("invest_orders", "expires_at")
