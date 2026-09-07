"""link opportunities to pre-trade checks

Revision ID: 202609070001
Revises: 202609030001
Create Date: 2026-09-07

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202609070001"
down_revision: str | None = "202609030001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column(
            "pre_trade_risk_check_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_opportunities_pre_trade_risk_check_id"),
        "opportunities",
        ["pre_trade_risk_check_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_opportunities_pre_trade_risk_check_id",
        "opportunities",
        "pre_trade_risk_checks",
        ["pre_trade_risk_check_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_opportunities_pre_trade_risk_check_id",
        "opportunities",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_opportunities_pre_trade_risk_check_id"),
        table_name="opportunities",
    )
    op.drop_column("opportunities", "pre_trade_risk_check_id")
