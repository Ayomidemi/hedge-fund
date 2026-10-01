"""add idempotency keys for money writes

Revision ID: 202610010001
Revises: 202609250001
Create Date: 2026-10-01

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202610010001"
down_revision: str | None = "202609250001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_key(table: str, index_name: str, *columns: str) -> None:
    op.add_column(table, sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index(
        index_name,
        table,
        list(columns),
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def upgrade() -> None:
    _add_key(
        "invest_orders",
        "uq_invest_orders_account_idempotency_key",
        "account_id",
        "idempotency_key",
    )
    _add_key(
        "invest_transactions",
        "uq_invest_transactions_account_idempotency_key",
        "account_id",
        "idempotency_key",
    )
    _add_key(
        "cash_ledger_entries",
        "uq_cash_ledger_entries_portfolio_idempotency_key",
        "portfolio_id",
        "idempotency_key",
    )
    _add_key(
        "trades",
        "uq_trades_portfolio_idempotency_key",
        "portfolio_id",
        "idempotency_key",
    )
    _add_key(
        "opportunities",
        "uq_opportunities_owner_idempotency_key",
        "owner_user_id",
        "idempotency_key",
    )


def downgrade() -> None:
    for table, index_name in (
        ("opportunities", "uq_opportunities_owner_idempotency_key"),
        ("trades", "uq_trades_portfolio_idempotency_key"),
        ("cash_ledger_entries", "uq_cash_ledger_entries_portfolio_idempotency_key"),
        ("invest_transactions", "uq_invest_transactions_account_idempotency_key"),
        ("invest_orders", "uq_invest_orders_account_idempotency_key"),
    ):
        op.drop_index(index_name, table_name=table)
        op.drop_column(table, "idempotency_key")
