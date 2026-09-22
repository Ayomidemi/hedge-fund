"""add invest fixed income registry

Revision ID: 202609220001
Revises: 202609210001
Create Date: 2026-09-22

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202609220001"
down_revision: str | None = "202609210001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invest_fixed_income_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column(
            "currency", sa.String(length=3), nullable=False, server_default="USD"
        ),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("instrument_type", sa.String(length=64), nullable=False),
        sa.Column("tenor", sa.String(length=64), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("maturity_days", sa.Integer(), nullable=True),
        sa.Column("indicative_yield_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("coupon_rate_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("coupon_frequency_per_year", sa.Integer(), nullable=False),
        sa.Column("settlement_days", sa.Integer(), nullable=False),
        sa.Column("minimum_order_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("face_value_increment", sa.Numeric(18, 4), nullable=False),
        sa.Column("liquidity", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=64), nullable=False),
        sa.Column("expected_payout", sa.Text(), nullable=False),
        sa.Column("trade_status", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("proxy_ticker", sa.String(length=32), nullable=True),
        sa.Column("proxy_label", sa.String(length=128), nullable=True),
        sa.Column(
            "retail_notes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "day_count_convention",
            sa.String(length=32),
            nullable=False,
            server_default="ACT/365",
        ),
        sa.Column(
            "compounding_basis",
            sa.String(length=32),
            nullable=False,
            server_default="simple",
        ),
        sa.Column(
            "quote_source",
            sa.String(length=64),
            nullable=False,
            server_default="model_seed",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", name="uq_invest_fixed_income_products_ticker"),
    )
    op.create_index(
        "ix_invest_fixed_income_products_ticker",
        "invest_fixed_income_products",
        ["ticker"],
    )
    op.create_index(
        "ix_invest_fixed_income_products_active_market",
        "invest_fixed_income_products",
        ["is_active", "market", "instrument_type"],
    )

    op.create_table(
        "invest_fixed_income_quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("yield_to_maturity_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("clean_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("accrued_interest", sa.Numeric(18, 6), nullable=True),
        sa.Column("dirty_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("settlement_date", sa.Date(), nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("days_to_maturity", sa.Integer(), nullable=True),
        sa.Column("next_coupon_date", sa.Date(), nullable=True),
        sa.Column("face_value_increment", sa.Numeric(18, 4), nullable=True),
        sa.Column("quote_status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stale_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "assumptions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
        sa.ForeignKeyConstraint(["product_id"], ["invest_fixed_income_products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_invest_fixed_income_quotes_product_id",
        "invest_fixed_income_quotes",
        ["product_id"],
    )
    op.create_index(
        "ix_invest_fixed_income_quotes_product_asof",
        "invest_fixed_income_quotes",
        ["product_id", "source_as_of"],
    )
    op.create_index(
        "ix_invest_fixed_income_quotes_stale_after",
        "invest_fixed_income_quotes",
        ["stale_after"],
    )

    op.create_table(
        "invest_yield_curves",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("curve_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market",
            "currency",
            "curve_date",
            "source",
            name="uq_invest_yield_curve_market_date_source",
        ),
    )
    op.create_index(
        "ix_invest_yield_curves_market_date",
        "invest_yield_curves",
        ["market", "curve_date"],
    )

    op.create_table(
        "invest_yield_curve_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("curve_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenor", sa.String(length=32), nullable=False),
        sa.Column("days_to_maturity", sa.Integer(), nullable=False),
        sa.Column("yield_pct", sa.Numeric(10, 4), nullable=False),
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
        sa.ForeignKeyConstraint(["curve_id"], ["invest_yield_curves.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "curve_id",
            "tenor",
            name="uq_invest_yield_curve_points_curve_tenor",
        ),
    )
    op.create_index(
        "ix_invest_yield_curve_points_curve_id",
        "invest_yield_curve_points",
        ["curve_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_invest_yield_curve_points_curve_id",
        table_name="invest_yield_curve_points",
    )
    op.drop_table("invest_yield_curve_points")
    op.drop_index(
        "ix_invest_yield_curves_market_date",
        table_name="invest_yield_curves",
    )
    op.drop_table("invest_yield_curves")
    op.drop_index(
        "ix_invest_fixed_income_quotes_stale_after",
        table_name="invest_fixed_income_quotes",
    )
    op.drop_index(
        "ix_invest_fixed_income_quotes_product_asof",
        table_name="invest_fixed_income_quotes",
    )
    op.drop_index(
        "ix_invest_fixed_income_quotes_product_id",
        table_name="invest_fixed_income_quotes",
    )
    op.drop_table("invest_fixed_income_quotes")
    op.drop_index(
        "ix_invest_fixed_income_products_active_market",
        table_name="invest_fixed_income_products",
    )
    op.drop_index(
        "ix_invest_fixed_income_products_ticker",
        table_name="invest_fixed_income_products",
    )
    op.drop_table("invest_fixed_income_products")
