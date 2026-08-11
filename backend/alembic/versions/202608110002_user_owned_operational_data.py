"""user owned operational data

Revision ID: 202608110002
Revises: 202608110001
Create Date: 2026-08-11 01:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202608110002"
down_revision: str | None = "202608110001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM ticker_feature_snapshots
        WHERE feature_version = 'ticker_features_v1'
        """
    )
    op.execute(
        """
        TRUNCATE TABLE
            risk_checks,
            trades,
            ticker_memos,
            human_model_decisions,
            evidence_snapshots,
            model_recommendations,
            position_risk_snapshots,
            risk_measurements,
            stress_test_results,
            stress_scenarios,
            portfolio_risk_snapshots,
            positions,
            cash_ledger_entries,
            risk_limits,
            portfolios,
            strategy_pod_snapshots,
            strategy_pods
        CASCADE
        """
    )

    op.drop_constraint("portfolios_name_key", "portfolios", type_="unique")
    op.drop_constraint("strategy_pods_code_key", "strategy_pods", type_="unique")

    op.add_column(
        "portfolios", sa.Column("owner_user_id", sa.String(length=64), nullable=False)
    )
    op.add_column(
        "model_recommendations",
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
    )
    op.add_column(
        "ticker_memos", sa.Column("owner_user_id", sa.String(length=64), nullable=False)
    )
    op.add_column(
        "strategy_pods",
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
    )
    op.add_column(
        "stress_scenarios",
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
    )

    op.create_index(
        "ix_portfolios_owner_user_id", "portfolios", ["owner_user_id"], unique=False
    )
    op.create_index(
        "ix_portfolios_owner_user_id_unique",
        "portfolios",
        ["owner_user_id"],
        unique=True,
    )
    op.create_index(
        "ix_portfolios_owner_name", "portfolios", ["owner_user_id", "name"], unique=True
    )
    op.create_index(
        "ix_model_recommendations_owner_user_id",
        "model_recommendations",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_ticker_memos_owner_user_id", "ticker_memos", ["owner_user_id"], unique=False
    )
    op.create_index(
        "ix_strategy_pods_owner_user_id",
        "strategy_pods",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_pods_owner_code",
        "strategy_pods",
        ["owner_user_id", "code"],
        unique=True,
    )
    op.create_index(
        "ix_stress_scenarios_owner_user_id",
        "stress_scenarios",
        ["owner_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stress_scenarios_owner_user_id", table_name="stress_scenarios")
    op.drop_index("ix_strategy_pods_owner_code", table_name="strategy_pods")
    op.drop_index("ix_strategy_pods_owner_user_id", table_name="strategy_pods")
    op.drop_index("ix_ticker_memos_owner_user_id", table_name="ticker_memos")
    op.drop_index(
        "ix_model_recommendations_owner_user_id", table_name="model_recommendations"
    )
    op.drop_index("ix_portfolios_owner_name", table_name="portfolios")
    op.drop_index("ix_portfolios_owner_user_id_unique", table_name="portfolios")
    op.drop_index("ix_portfolios_owner_user_id", table_name="portfolios")

    op.drop_column("stress_scenarios", "owner_user_id")
    op.drop_column("strategy_pods", "owner_user_id")
    op.drop_column("ticker_memos", "owner_user_id")
    op.drop_column("model_recommendations", "owner_user_id")
    op.drop_column("portfolios", "owner_user_id")

    op.create_unique_constraint("strategy_pods_code_key", "strategy_pods", ["code"])
    op.create_unique_constraint("portfolios_name_key", "portfolios", ["name"])
