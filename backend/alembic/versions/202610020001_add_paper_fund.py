"""Isolated, automatic $10k paper fund trials.

Revision ID: 202610020001
Revises: 202610010001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "202610020001"
down_revision = "202610010001"
branch_labels = None
depends_on = None


def _id():
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def _money(name, nullable=False):
    return sa.Column(name, sa.Numeric(18, 2), nullable=nullable)


def _time(name, nullable=True):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _timestamps():
    return [sa.Column(n, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
            for n in ("created_at", "updated_at")]


def upgrade():
    op.create_table(
        "paper_fund_runs", _id(),
        sa.Column("owner_user_id", sa.String(64), nullable=False),
        sa.Column("start_key", sa.String(128)),
        sa.Column("status", sa.String(24), nullable=False),
        _money("starting_cash"), _money("cash_balance"), _money("high_water_equity"),
        sa.Column("max_drawdown_pct", sa.Numeric(12, 6), nullable=False),
        _time("started_at", False), _time("ends_at", False), _time("last_cycle_at"), _time("completed_at"),
        sa.Column("halt_reason", sa.Text()),
        sa.Column("policy", pg.JSONB(), nullable=False),
        sa.Column("blockers", pg.JSONB(), nullable=False), *_timestamps(),
        sa.CheckConstraint("starting_cash > 0 AND cash_balance >= 0", name="ck_paper_fund_capital"),
        sa.CheckConstraint("status IN ('running','paused','liquidating','completed','halted')", name="ck_paper_fund_status"),
    )
    op.create_index("ix_paper_fund_runs_owner_user_id", "paper_fund_runs", ["owner_user_id"])
    op.create_index("uq_paper_fund_start_key", "paper_fund_runs", ["owner_user_id", "start_key"], unique=True)
    op.create_index("uq_paper_fund_active_owner", "paper_fund_runs", ["owner_user_id"], unique=True,
                    postgresql_where=sa.text("status <> 'completed'"))
    op.create_table(
        "paper_orders", _id(),
        sa.Column("run_id", pg.UUID(as_uuid=True), sa.ForeignKey("paper_fund_runs.id"), nullable=False),
        sa.Column("instrument_id", pg.UUID(as_uuid=True), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False), sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(128)), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        *[_money(n) for n in ("limit_price", "stop_price", "target_price")],
        _money("entry_price", True), _money("exit_price", True),
        sa.Column("mark_price", sa.Numeric(18, 6)),
        *[_money(n) for n in ("entry_fee", "exit_fee", "realized_pnl")],
        _time("submitted_at", False), _time("expires_at", False),
        *[_time(n) for n in ("opened_at", "closed_at", "entry_quote_at", "exit_quote_at", "mark_as_of")],
        sa.Column("exit_reason", sa.String(255)), sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("evidence", pg.JSONB(), nullable=False), *_timestamps(),
        sa.CheckConstraint("quantity > 0 AND stop_price > 0 AND stop_price < limit_price AND target_price > limit_price", name="ck_paper_order_plan"),
        sa.CheckConstraint("status IN ('pending','open','closed','cancelled','expired')", name="ck_paper_order_status"),
    )
    op.create_index("ix_paper_orders_run_id", "paper_orders", ["run_id"])
    op.create_index("uq_paper_order_run_instrument", "paper_orders", ["run_id", "instrument_id"], unique=True)
    op.create_table(
        "paper_equity_snapshots", _id(),
        sa.Column("run_id", pg.UUID(as_uuid=True), sa.ForeignKey("paper_fund_runs.id"), nullable=False),
        _time("recorded_at", False),
        *[_money(n) for n in ("equity", "cash_balance", "realized_pnl", "unrealized_pnl")],
        sa.Column("drawdown_pct", sa.Numeric(12, 6), nullable=False),
    )
    op.create_index("ix_paper_equity_snapshots_run_id", "paper_equity_snapshots", ["run_id"])
    op.create_index("ix_paper_equity_run_time", "paper_equity_snapshots", ["run_id", "recorded_at"])


def downgrade():
    op.drop_table("paper_equity_snapshots")
    op.drop_table("paper_orders")
    op.drop_table("paper_fund_runs")
