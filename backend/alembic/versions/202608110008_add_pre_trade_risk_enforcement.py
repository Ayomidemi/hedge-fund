"""add pre-trade risk enforcement

Revision ID: 202608110008
Revises: 202608110007
Create Date: 2026-08-14 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608110008"
down_revision: str | None = "202608110007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pre_trade_risk_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("cash_impact", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "request_fingerprint",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "result_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("messages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pre_trade_risk_checks_owner_checked",
        "pre_trade_risk_checks",
        ["owner_user_id", "checked_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pre_trade_risk_checks_owner_user_id"),
        "pre_trade_risk_checks",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pre_trade_risk_checks_portfolio_id"),
        "pre_trade_risk_checks",
        ["portfolio_id"],
        unique=False,
    )

    op.add_column(
        "trades",
        sa.Column(
            "pre_trade_risk_check_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "trades", sa.Column("risk_decision", sa.String(length=32), nullable=True)
    )
    op.add_column("trades", sa.Column("risk_override_reason", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_trades_pre_trade_risk_check_id"),
        "trades",
        ["pre_trade_risk_check_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_trades_pre_trade_risk_check_id",
        "trades",
        "pre_trade_risk_checks",
        ["pre_trade_risk_check_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_trades_pre_trade_risk_check_id",
        "trades",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_trades_pre_trade_risk_check_id"), table_name="trades")
    op.drop_column("trades", "risk_override_reason")
    op.drop_column("trades", "risk_decision")
    op.drop_column("trades", "pre_trade_risk_check_id")

    op.drop_index(
        op.f("ix_pre_trade_risk_checks_portfolio_id"),
        table_name="pre_trade_risk_checks",
    )
    op.drop_index(
        op.f("ix_pre_trade_risk_checks_owner_user_id"),
        table_name="pre_trade_risk_checks",
    )
    op.drop_index(
        "ix_pre_trade_risk_checks_owner_checked",
        table_name="pre_trade_risk_checks",
    )
    op.drop_table("pre_trade_risk_checks")
