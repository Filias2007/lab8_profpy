"""add product description

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 12:30:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def _product_columns() -> set[str]:
    if context.is_offline_mode():
        return set()
    columns = sa.inspect(op.get_bind()).get_columns("products")
    return {column["name"] for column in columns}


def upgrade() -> None:
    # Skip when the table was created by Base.metadata.create_all()
    # and already contains the column.
    if "description" not in _product_columns():
        op.add_column(
            "products",
            sa.Column("description", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("products", "description")
