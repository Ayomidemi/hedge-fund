"""add risk centre foundation

Revision ID: 202608100001
Revises: 202608060001
Create Date: 2026-08-10 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608100001"
down_revision: str | None = "202608060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_policy_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hierarchy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_policy_versions_name_version",
        "risk_policy_versions",
        ["name", "version"],
        unique=True,
    )

    op.create_table(
        "portfolio_risk_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("risk_policy_version_id", sa.UUID(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("nav", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("cash_balance", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("invested_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("gross_exposure_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("net_exposure_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("cash_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("top_position_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("top5_concentration_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("portfolio_volatility_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("beta_to_benchmark", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("max_drawdown_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("var_95_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("expected_shortfall_95_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("liquidity_days", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("exposures", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["risk_policy_version_id"], ["risk_policy_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_portfolio_risk_snapshots_as_of_date"), "portfolio_risk_snapshots", ["as_of_date"], unique=False)
    op.create_index(op.f("ix_portfolio_risk_snapshots_portfolio_id"), "portfolio_risk_snapshots", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_portfolio_risk_snapshots_risk_policy_version_id"), "portfolio_risk_snapshots", ["risk_policy_version_id"], unique=False)
    op.create_index("ix_portfolio_risk_snapshots_portfolio_captured", "portfolio_risk_snapshots", ["portfolio_id", "captured_at"], unique=False)

    op.create_table(
        "position_risk_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_risk_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("market_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("weight_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("volatility_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("beta_to_benchmark", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("liquidity_days", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["portfolio_risk_snapshot_id"], ["portfolio_risk_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_position_risk_snapshots_instrument_id"), "position_risk_snapshots", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_position_risk_snapshots_portfolio_id"), "position_risk_snapshots", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_position_risk_snapshots_portfolio_risk_snapshot_id"), "position_risk_snapshots", ["portfolio_risk_snapshot_id"], unique=False)
    op.create_index("ix_position_risk_snapshots_snapshot_ticker", "position_risk_snapshots", ["portfolio_risk_snapshot_id", "ticker"], unique=False)

    op.create_table(
        "risk_measurements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("portfolio_risk_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measurement_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("threshold_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["portfolio_risk_snapshot_id"], ["portfolio_risk_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_measurements_portfolio_id"), "risk_measurements", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_risk_measurements_portfolio_risk_snapshot_id"), "risk_measurements", ["portfolio_risk_snapshot_id"], unique=False)
    op.create_index("ix_risk_measurements_portfolio_measured", "risk_measurements", ["portfolio_id", "measured_at"], unique=False)

    op.create_table(
        "stress_scenarios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("scenario_type", sa.String(length=64), nullable=False),
        sa.Column("shocks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "stress_test_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("portfolio_risk_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("stress_scenario_id", sa.UUID(), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scenario_name", sa.String(length=128), nullable=False),
        sa.Column("nav_before", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("nav_after", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("nav_impact_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("worst_positions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["portfolio_risk_snapshot_id"], ["portfolio_risk_snapshots.id"]),
        sa.ForeignKeyConstraint(["stress_scenario_id"], ["stress_scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stress_test_results_portfolio_id"), "stress_test_results", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_stress_test_results_portfolio_risk_snapshot_id"), "stress_test_results", ["portfolio_risk_snapshot_id"], unique=False)
    op.create_index(op.f("ix_stress_test_results_stress_scenario_id"), "stress_test_results", ["stress_scenario_id"], unique=False)
    op.create_index("ix_stress_test_results_portfolio_run", "stress_test_results", ["portfolio_id", "run_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stress_test_results_portfolio_run", table_name="stress_test_results")
    op.drop_index(op.f("ix_stress_test_results_stress_scenario_id"), table_name="stress_test_results")
    op.drop_index(op.f("ix_stress_test_results_portfolio_risk_snapshot_id"), table_name="stress_test_results")
    op.drop_index(op.f("ix_stress_test_results_portfolio_id"), table_name="stress_test_results")
    op.drop_table("stress_test_results")
    op.drop_table("stress_scenarios")
    op.drop_index("ix_risk_measurements_portfolio_measured", table_name="risk_measurements")
    op.drop_index(op.f("ix_risk_measurements_portfolio_risk_snapshot_id"), table_name="risk_measurements")
    op.drop_index(op.f("ix_risk_measurements_portfolio_id"), table_name="risk_measurements")
    op.drop_table("risk_measurements")
    op.drop_index("ix_position_risk_snapshots_snapshot_ticker", table_name="position_risk_snapshots")
    op.drop_index(op.f("ix_position_risk_snapshots_portfolio_risk_snapshot_id"), table_name="position_risk_snapshots")
    op.drop_index(op.f("ix_position_risk_snapshots_portfolio_id"), table_name="position_risk_snapshots")
    op.drop_index(op.f("ix_position_risk_snapshots_instrument_id"), table_name="position_risk_snapshots")
    op.drop_table("position_risk_snapshots")
    op.drop_index("ix_portfolio_risk_snapshots_portfolio_captured", table_name="portfolio_risk_snapshots")
    op.drop_index(op.f("ix_portfolio_risk_snapshots_risk_policy_version_id"), table_name="portfolio_risk_snapshots")
    op.drop_index(op.f("ix_portfolio_risk_snapshots_portfolio_id"), table_name="portfolio_risk_snapshots")
    op.drop_index(op.f("ix_portfolio_risk_snapshots_as_of_date"), table_name="portfolio_risk_snapshots")
    op.drop_table("portfolio_risk_snapshots")
    op.drop_index("ix_risk_policy_versions_name_version", table_name="risk_policy_versions")
    op.drop_table("risk_policy_versions")
