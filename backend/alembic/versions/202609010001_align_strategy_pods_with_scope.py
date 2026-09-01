"""align strategy pods with scope section 24

Revision ID: 202609010001
Revises: 202608240004
Create Date: 2026-09-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609010001"
down_revision: Union[str, None] = "202608240004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "strategy_pods",
        sa.Column("pod_category", sa.String(length=32), nullable=False, server_default="alpha"),
    )
    op.add_column(
        "strategy_pods",
        sa.Column("live_scope", sa.String(length=32), nullable=False, server_default="research"),
    )
    op.create_index(
        op.f("ix_strategy_pods_pod_category"),
        "strategy_pods",
        ["pod_category"],
        unique=False,
    )

    op.execute(
        """
        UPDATE strategy_pods
        SET pod_category = 'alpha',
            live_scope = CASE code
                WHEN 'macro_regime' THEN 'yes'
                WHEN 'cross_asset_trend' THEN 'yes'
                WHEN 'quant_equity' THEN 'yes'
                WHEN 'fundamental_equity' THEN 'yes'
                WHEN 'relative_value' THEN 'limited'
                WHEN 'experimental_research' THEN 'research'
                ELSE 'research'
            END
        """
    )

    op.execute(
        """
        UPDATE strategy_pods
        SET status = 'retired',
            lifecycle_stage = 'retired',
            notes = COALESCE(notes, '') || ' Retired: sandbox ideas now live in Research Lab (SCOPE §24).'
        WHERE code = 'experimental_research'
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_strategy_pods_pod_category"), table_name="strategy_pods")
    op.drop_column("strategy_pods", "live_scope")
    op.drop_column("strategy_pods", "pod_category")
