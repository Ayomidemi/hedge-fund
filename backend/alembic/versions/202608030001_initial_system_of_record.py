"""initial system of record

Revision ID: 202608030001
Revises:
Create Date: 2026-08-03 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608030001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker"),
    )
    op.create_index(op.f("ix_instruments_ticker"), "instruments", ["ticker"], unique=False)

    op.create_table(
        "model_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("pod", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("training_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assumptions", sa.Text(), nullable=True),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("approved_use", sa.Text(), nullable=True),
        sa.Column("prohibited_use", sa.Text(), nullable=True),
        sa.Column("shutdown_criteria", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_versions_name_version", "model_versions", ["name", "version"], unique=True)

    op.create_table(
        "portfolios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("mandate", sa.Text(), nullable=True),
        sa.Column("initial_capital", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "cash_ledger_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("entry_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cash_ledger_entries_portfolio_id"), "cash_ledger_entries", ["portfolio_id"], unique=False)

    op.create_table(
        "model_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model_version_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("conviction_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("recommended_weight", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("time_horizon", sa.String(length=64), nullable=True),
        sa.Column("thesis", sa.Text(), nullable=True),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_recommendations_instrument_id"), "model_recommendations", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_model_recommendations_model_version_id"), "model_recommendations", ["model_version_id"], unique=False)

    op.create_table(
        "positions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("average_cost", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("market_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_positions_instrument_id"), "positions", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_positions_portfolio_id"), "positions", ["portfolio_id"], unique=False)

    op.create_table(
        "risk_limits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("limit_type", sa.String(length=64), nullable=False),
        sa.Column("threshold_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_limits_portfolio_id"), "risk_limits", ["portfolio_id"], unique=False)

    op.create_table(
        "evidence_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("recommendation_id", sa.UUID(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_reference", sa.String(length=512), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_version", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_id"], ["model_recommendations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evidence_snapshots_recommendation_id"), "evidence_snapshots", ["recommendation_id"], unique=False)

    op.create_table(
        "human_model_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("recommendation_id", sa.UUID(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("selected_action", sa.String(length=32), nullable=True),
        sa.Column("selected_weight", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.String(length=128), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_id"], ["model_recommendations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_human_model_decisions_recommendation_id"), "human_model_decisions", ["recommendation_id"], unique=False)

    op.create_table(
        "ticker_memos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("recommendation_id", sa.UUID(), nullable=True),
        sa.Column("memo_date", sa.Date(), nullable=False),
        sa.Column("classification", sa.String(length=64), nullable=False),
        sa.Column("time_horizon", sa.String(length=64), nullable=True),
        sa.Column("executive_view", sa.Text(), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("bull_case", sa.Text(), nullable=True),
        sa.Column("base_case", sa.Text(), nullable=True),
        sa.Column("bear_case", sa.Text(), nullable=True),
        sa.Column("thesis_breakers", sa.Text(), nullable=True),
        sa.Column("risk_assessment", sa.Text(), nullable=True),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version_label", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["recommendation_id"], ["model_recommendations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ticker_memos_instrument_id"), "ticker_memos", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_ticker_memos_recommendation_id"), "ticker_memos", ["recommendation_id"], unique=False)

    op.create_table(
        "trades",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("recommendation_id", sa.UUID(), nullable=True),
        sa.Column("trade_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("executed_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("fees", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("risk_notes", sa.Text(), nullable=True),
        sa.Column("broker_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["recommendation_id"], ["model_recommendations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trades_instrument_id"), "trades", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_trades_portfolio_id"), "trades", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_trades_recommendation_id"), "trades", ["recommendation_id"], unique=False)

    op.create_table(
        "risk_checks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("risk_limit_id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=True),
        sa.Column("recommendation_id", sa.UUID(), nullable=True),
        sa.Column("trade_id", sa.UUID(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["recommendation_id"], ["model_recommendations.id"]),
        sa.ForeignKeyConstraint(["risk_limit_id"], ["risk_limits.id"]),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_checks_portfolio_id"), "risk_checks", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_risk_checks_recommendation_id"), "risk_checks", ["recommendation_id"], unique=False)
    op.create_index(op.f("ix_risk_checks_risk_limit_id"), "risk_checks", ["risk_limit_id"], unique=False)
    op.create_index(op.f("ix_risk_checks_trade_id"), "risk_checks", ["trade_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_risk_checks_trade_id"), table_name="risk_checks")
    op.drop_index(op.f("ix_risk_checks_risk_limit_id"), table_name="risk_checks")
    op.drop_index(op.f("ix_risk_checks_recommendation_id"), table_name="risk_checks")
    op.drop_index(op.f("ix_risk_checks_portfolio_id"), table_name="risk_checks")
    op.drop_table("risk_checks")
    op.drop_index(op.f("ix_trades_recommendation_id"), table_name="trades")
    op.drop_index(op.f("ix_trades_portfolio_id"), table_name="trades")
    op.drop_index(op.f("ix_trades_instrument_id"), table_name="trades")
    op.drop_table("trades")
    op.drop_index(op.f("ix_ticker_memos_recommendation_id"), table_name="ticker_memos")
    op.drop_index(op.f("ix_ticker_memos_instrument_id"), table_name="ticker_memos")
    op.drop_table("ticker_memos")
    op.drop_index(op.f("ix_human_model_decisions_recommendation_id"), table_name="human_model_decisions")
    op.drop_table("human_model_decisions")
    op.drop_index(op.f("ix_evidence_snapshots_recommendation_id"), table_name="evidence_snapshots")
    op.drop_table("evidence_snapshots")
    op.drop_index(op.f("ix_risk_limits_portfolio_id"), table_name="risk_limits")
    op.drop_table("risk_limits")
    op.drop_index(op.f("ix_positions_portfolio_id"), table_name="positions")
    op.drop_index(op.f("ix_positions_instrument_id"), table_name="positions")
    op.drop_table("positions")
    op.drop_index(op.f("ix_model_recommendations_model_version_id"), table_name="model_recommendations")
    op.drop_index(op.f("ix_model_recommendations_instrument_id"), table_name="model_recommendations")
    op.drop_table("model_recommendations")
    op.drop_index(op.f("ix_cash_ledger_entries_portfolio_id"), table_name="cash_ledger_entries")
    op.drop_table("cash_ledger_entries")
    op.drop_table("portfolios")
    op.drop_index("ix_model_versions_name_version", table_name="model_versions")
    op.drop_table("model_versions")
    op.drop_index(op.f("ix_instruments_ticker"), table_name="instruments")
    op.drop_table("instruments")
