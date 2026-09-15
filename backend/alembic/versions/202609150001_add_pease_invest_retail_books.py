"""add pease invest retail books

Revision ID: 202609150001
Revises: 202609070001
Create Date: 2026-09-15

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202609150001"
down_revision: str | None = "202609070001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invest_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("account_number", sa.String(length=32), nullable=False),
        sa.Column("broker_provider", sa.String(length=32), nullable=False),
        sa.Column("broker_account_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("cash_balance", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", name="uq_invest_accounts_user_id"),
        sa.UniqueConstraint("account_number", name="uq_invest_accounts_number"),
    )
    op.create_index("ix_invest_accounts_user_id", "invest_accounts", ["user_id"])
    op.create_index(
        "ix_invest_accounts_broker",
        "invest_accounts",
        ["broker_provider", "broker_account_id"],
    )

    op.create_table(
        "invest_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("notional", sa.Numeric(18, 4), nullable=True),
        sa.Column("limit_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("average_fill_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("filled_quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("broker_provider", sa.String(length=32), nullable=False),
        sa.Column("broker_order_id", sa.String(length=64), nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["invest_accounts.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.UniqueConstraint(
            "broker_provider",
            "broker_order_id",
            name="uq_invest_broker_order",
        ),
    )
    op.create_index("ix_invest_orders_user_id", "invest_orders", ["user_id"])
    op.create_index("ix_invest_orders_account_id", "invest_orders", ["account_id"])
    op.create_index(
        "ix_invest_orders_instrument_id", "invest_orders", ["instrument_id"]
    )
    op.create_index(
        "ix_invest_orders_account_submitted",
        "invest_orders",
        ["account_id", "submitted_at"],
    )

    op.create_table(
        "invest_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("average_cost", sa.Numeric(18, 6), nullable=False),
        sa.Column("cost_basis", sa.Numeric(18, 4), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["invest_accounts.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.UniqueConstraint(
            "account_id",
            "instrument_id",
            name="uq_invest_position_instrument",
        ),
    )
    op.create_index(
        "ix_invest_positions_account_id", "invest_positions", ["account_id"]
    )
    op.create_index(
        "ix_invest_positions_instrument_id", "invest_positions", ["instrument_id"]
    )

    op.create_table(
        "invest_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("broker_reference", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["invest_accounts.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
    )
    op.create_index(
        "ix_invest_transactions_account_id", "invest_transactions", ["account_id"]
    )
    op.create_index(
        "ix_invest_transactions_instrument_id",
        "invest_transactions",
        ["instrument_id"],
    )
    op.create_index(
        "ix_invest_transactions_account_occurred",
        "invest_transactions",
        ["account_id", "occurred_at"],
    )

    op.create_table(
        "invest_watchlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("date_added", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.UniqueConstraint(
            "user_id",
            "instrument_id",
            name="uq_invest_watchlist_instrument",
        ),
    )
    op.create_index(
        "ix_invest_watchlist_items_user_id", "invest_watchlist_items", ["user_id"]
    )
    op.create_index(
        "ix_invest_watchlist_items_instrument_id",
        "invest_watchlist_items",
        ["instrument_id"],
    )


def downgrade() -> None:
    op.drop_table("invest_watchlist_items")
    op.drop_table("invest_transactions")
    op.drop_table("invest_positions")
    op.drop_table("invest_orders")
    op.drop_table("invest_accounts")
