"""add fixed income quote provenance

Revision ID: 202609230001
Revises: 202609220002
Create Date: 2026-09-23

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202609230001"
down_revision: str | None = "202609220002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column(
            "quote_provider",
            sa.String(length=64),
            nullable=False,
            server_default="internal_model",
        ),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column(
            "quote_quality",
            sa.String(length=32),
            nullable=False,
            server_default="seed_model",
        ),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column(
            "quote_type",
            sa.String(length=32),
            nullable=False,
            server_default="model",
        ),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column("provider_security_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column("bid_price", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column("ask_price", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column("mid_price", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column("last_price", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column("bid_yield_pct", sa.Numeric(10, 4), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column("ask_yield_pct", sa.Numeric(10, 4), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column("mid_yield_pct", sa.Numeric(10, 4), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column("last_yield_pct", sa.Numeric(10, 4), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_quotes",
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_invest_fixed_income_quotes_provider_quality",
        "invest_fixed_income_quotes",
        ["quote_provider", "quote_quality"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_invest_fixed_income_quotes_provider_quality",
        table_name="invest_fixed_income_quotes",
    )
    op.drop_column("invest_fixed_income_quotes", "raw_payload")
    op.drop_column("invest_fixed_income_quotes", "last_yield_pct")
    op.drop_column("invest_fixed_income_quotes", "mid_yield_pct")
    op.drop_column("invest_fixed_income_quotes", "ask_yield_pct")
    op.drop_column("invest_fixed_income_quotes", "bid_yield_pct")
    op.drop_column("invest_fixed_income_quotes", "last_price")
    op.drop_column("invest_fixed_income_quotes", "mid_price")
    op.drop_column("invest_fixed_income_quotes", "ask_price")
    op.drop_column("invest_fixed_income_quotes", "bid_price")
    op.drop_column("invest_fixed_income_quotes", "provider_security_id")
    op.drop_column("invest_fixed_income_quotes", "quote_type")
    op.drop_column("invest_fixed_income_quotes", "quote_quality")
    op.drop_column("invest_fixed_income_quotes", "quote_provider")
