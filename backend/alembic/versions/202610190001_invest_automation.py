"""Invest automatic plans, cash reservations and durable realized P&L."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "202610190001"
down_revision = "202610160001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "invest_accounts",
        sa.Column("realized_pnl", sa.Numeric(18, 4), nullable=False, server_default="0"),
    )
    op.add_column(
        "invest_accounts",
        sa.Column("trading_mode", sa.String(16), nullable=False, server_default="manual"),
    )
    op.add_column(
        "invest_accounts",
        sa.Column("reserved_cash", sa.Numeric(18, 4), nullable=False, server_default="0"),
    )
    op.add_column("invest_accounts", sa.Column("high_water_equity", sa.Numeric(18, 4)))
    op.add_column(
        "invest_accounts",
        sa.Column("max_drawdown_pct", sa.Numeric(12, 6), nullable=False, server_default="0"),
    )
    op.add_column(
        "invest_accounts",
        sa.Column("automation_status", sa.String(24), nullable=False, server_default="idle"),
    )
    op.add_column("invest_accounts", sa.Column("halt_reason", sa.Text()))
    op.add_column("invest_accounts", sa.Column("last_cycle_at", sa.DateTime(timezone=True)))
    op.add_column(
        "invest_accounts",
        sa.Column(
            "automation_blockers",
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_invest_account_trading_mode",
        "invest_accounts",
        "trading_mode IN ('manual','automatic')",
    )
    op.create_check_constraint(
        "ck_invest_account_automation_status",
        "invest_accounts",
        "automation_status IN ('idle','running','paused','halted')",
    )
    op.create_check_constraint(
        "ck_invest_account_reserved_cash",
        "invest_accounts",
        "reserved_cash >= 0",
    )
    # Closed positions have already dropped their realized P&L. Keep whatever
    # partial result is still sitting on an open position.
    op.execute(
        """UPDATE invest_accounts AS account
           SET realized_pnl = COALESCE((
               SELECT SUM(position.realized_pnl)
               FROM invest_positions AS position
               WHERE position.account_id = account.id
           ), 0)"""
    )
    op.add_column(
        "invest_orders",
        sa.Column("origin", sa.String(16), nullable=False, server_default="manual"),
    )
    op.create_table(
        "invest_managed_orders",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", pg.UUID(as_uuid=True), sa.ForeignKey("invest_accounts.id"), nullable=False),
        sa.Column("instrument_id", pg.UUID(as_uuid=True), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("signal_id", pg.UUID(as_uuid=True)),
        sa.Column("entry_order_id", pg.UUID(as_uuid=True), sa.ForeignKey("invest_orders.id")),
        sa.Column("exit_order_id", pg.UUID(as_uuid=True), sa.ForeignKey("invest_orders.id")),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(128)),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("limit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("stop_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("target_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 6)),
        sa.Column("exit_price", sa.Numeric(18, 6)),
        sa.Column("mark_price", sa.Numeric(18, 6)),
        sa.Column("entry_fee", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("exit_fee", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("reserved_cash", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("entry_quote_at", sa.DateTime(timezone=True)),
        sa.Column("exit_quote_at", sa.DateTime(timezone=True)),
        sa.Column("mark_as_of", sa.DateTime(timezone=True)),
        sa.Column("exit_reason", sa.String(255)),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("evidence", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "quantity > 0 AND stop_price > 0 AND stop_price < limit_price AND target_price > limit_price",
            name="ck_invest_managed_plan",
        ),
        sa.CheckConstraint(
            "status IN ('pending','open','closed','cancelled','expired')",
            name="ck_invest_managed_status",
        ),
        sa.CheckConstraint("reserved_cash >= 0", name="ck_invest_managed_reserved"),
    )
    op.create_index("ix_invest_managed_orders_account_id", "invest_managed_orders", ["account_id"])
    op.create_index(
        "uq_invest_managed_active",
        "invest_managed_orders",
        ["account_id", "instrument_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','open')"),
    )
    op.create_index(
        "uq_invest_managed_signal",
        "invest_managed_orders",
        ["account_id", "instrument_id", "signal_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_invest_managed_signal", table_name="invest_managed_orders")
    op.drop_index("uq_invest_managed_active", table_name="invest_managed_orders")
    op.drop_index("ix_invest_managed_orders_account_id", table_name="invest_managed_orders")
    op.drop_table("invest_managed_orders")
    op.drop_column("invest_orders", "origin")
    op.drop_constraint("ck_invest_account_reserved_cash", "invest_accounts", type_="check")
    op.drop_constraint("ck_invest_account_automation_status", "invest_accounts", type_="check")
    op.drop_constraint("ck_invest_account_trading_mode", "invest_accounts", type_="check")
    op.drop_column("invest_accounts", "automation_blockers")
    op.drop_column("invest_accounts", "last_cycle_at")
    op.drop_column("invest_accounts", "halt_reason")
    op.drop_column("invest_accounts", "automation_status")
    op.drop_column("invest_accounts", "max_drawdown_pct")
    op.drop_column("invest_accounts", "high_water_equity")
    op.drop_column("invest_accounts", "reserved_cash")
    op.drop_column("invest_accounts", "trading_mode")
    op.drop_column("invest_accounts", "realized_pnl")
