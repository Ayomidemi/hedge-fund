"""add ml training data

Revision ID: 202608060001
Revises: 202608050001
Create Date: 2026-08-06 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202608060001"
down_revision: str | None = "202608050001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_price_bars",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("bar_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("open_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("high_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("low_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("close_price", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("adjusted_close_price", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "bar_date",
            "source",
            name="uq_market_price_bars_instrument_date_source",
        ),
    )
    op.create_index(
        op.f("ix_market_price_bars_bar_date"),
        "market_price_bars",
        ["bar_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_market_price_bars_instrument_id"),
        "market_price_bars",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_market_price_bars_instrument_date",
        "market_price_bars",
        ["instrument_id", "bar_date"],
        unique=False,
    )

    op.create_table(
        "ticker_feature_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("source_reference", sa.String(length=512), nullable=True),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quality_score", sa.Numeric(precision=5, scale=2), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "as_of_date",
            "feature_version",
            name="uq_ticker_feature_snapshots_instrument_date_version",
        ),
    )
    op.create_index(
        op.f("ix_ticker_feature_snapshots_as_of_date"),
        "ticker_feature_snapshots",
        ["as_of_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticker_feature_snapshots_instrument_id"),
        "ticker_feature_snapshots",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_ticker_feature_snapshots_instrument_date",
        "ticker_feature_snapshots",
        ["instrument_id", "as_of_date"],
        unique=False,
    )

    op.create_table(
        "ticker_training_labels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("benchmark_instrument_id", sa.UUID(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("forward_return_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column(
            "benchmark_forward_return_pct",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
        ),
        sa.Column("relative_return_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("max_drawdown_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("realized_volatility_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("label_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(["benchmark_instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "benchmark_instrument_id",
            "as_of_date",
            "horizon_days",
            "label_version",
            "source",
            name="uq_ticker_training_labels_identity",
        ),
    )
    op.create_index(
        op.f("ix_ticker_training_labels_as_of_date"),
        "ticker_training_labels",
        ["as_of_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticker_training_labels_benchmark_instrument_id"),
        "ticker_training_labels",
        ["benchmark_instrument_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticker_training_labels_instrument_id"),
        "ticker_training_labels",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_ticker_training_labels_instrument_date",
        "ticker_training_labels",
        ["instrument_id", "as_of_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ticker_training_labels_instrument_date", table_name="ticker_training_labels")
    op.drop_index(op.f("ix_ticker_training_labels_instrument_id"), table_name="ticker_training_labels")
    op.drop_index(
        op.f("ix_ticker_training_labels_benchmark_instrument_id"),
        table_name="ticker_training_labels",
    )
    op.drop_index(op.f("ix_ticker_training_labels_as_of_date"), table_name="ticker_training_labels")
    op.drop_table("ticker_training_labels")

    op.drop_index("ix_ticker_feature_snapshots_instrument_date", table_name="ticker_feature_snapshots")
    op.drop_index(
        op.f("ix_ticker_feature_snapshots_instrument_id"),
        table_name="ticker_feature_snapshots",
    )
    op.drop_index(
        op.f("ix_ticker_feature_snapshots_as_of_date"),
        table_name="ticker_feature_snapshots",
    )
    op.drop_table("ticker_feature_snapshots")

    op.drop_index("ix_market_price_bars_instrument_date", table_name="market_price_bars")
    op.drop_index(op.f("ix_market_price_bars_instrument_id"), table_name="market_price_bars")
    op.drop_index(op.f("ix_market_price_bars_bar_date"), table_name="market_price_bars")
    op.drop_table("market_price_bars")
