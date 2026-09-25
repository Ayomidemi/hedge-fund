"""add fixed income product source metadata

Revision ID: 202609250001
Revises: 202609230001
Create Date: 2026-09-25

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202609250001"
down_revision: str | None = "202609230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invest_fixed_income_products",
        sa.Column("provider_security_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_products",
        sa.Column("source_as_of", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "invest_fixed_income_products",
        sa.Column(
            "source_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_invest_fixed_income_products_provider_security",
        "invest_fixed_income_products",
        ["quote_source", "provider_security_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_invest_fixed_income_products_provider_security",
        table_name="invest_fixed_income_products",
    )
    op.drop_column("invest_fixed_income_products", "source_payload")
    op.drop_column("invest_fixed_income_products", "source_as_of")
    op.drop_column("invest_fixed_income_products", "provider_security_id")
