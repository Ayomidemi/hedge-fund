"""opportunity strategy pod and parked status

Revision ID: 202609030001
Revises: 202609010001
Create Date: 2026-09-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609030001"
down_revision: Union[str, None] = "202609010001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("strategy_pod_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_opportunities_strategy_pod_id"),
        "opportunities",
        ["strategy_pod_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_opportunities_strategy_pod_id",
        "opportunities",
        "strategy_pods",
        ["strategy_pod_id"],
        ["id"],
    )

    op.execute(
        """
        UPDATE opportunities
        SET status = 'parked'
        WHERE status = 'watchlist'
        """
    )

    # Assign open opportunities to the owner's Fundamental / Catalyst pod when present.
    op.execute(
        """
        UPDATE opportunities AS o
        SET strategy_pod_id = p.id
        FROM strategy_pods AS p
        WHERE o.strategy_pod_id IS NULL
          AND o.owner_user_id = p.owner_user_id
          AND p.code = 'fundamental_equity'
          AND o.closed_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE opportunities
        SET status = 'watchlist'
        WHERE status = 'parked'
        """
    )
    op.drop_constraint(
        "fk_opportunities_strategy_pod_id", "opportunities", type_="foreignkey"
    )
    op.drop_index(op.f("ix_opportunities_strategy_pod_id"), table_name="opportunities")
    op.drop_column("opportunities", "strategy_pod_id")
