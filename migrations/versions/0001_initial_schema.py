"""initial schema: categories, products, purchases

Revision ID: 0001
Revises:
Create Date: 2026-10-25 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def _table_names() -> set[str]:
    """Names of existing tables (the baseline is skipped for existing ones)."""
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _table_names()

    if "categories" not in existing:
        op.create_table(
            "categories",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.UniqueConstraint("name"),
        )

    if "products" not in existing:
        op.create_table(
            "products",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column(
                "category_id",
                sa.Integer(),
                sa.ForeignKey("categories.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
            sa.CheckConstraint(
                "quantity >= 0", name="ck_products_quantity_non_negative"
            ),
        )

    if "purchases" not in existing:
        op.create_table(
            "purchases",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("total_price", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "quantity > 0", name="ck_purchases_quantity_positive"
            ),
        )


def downgrade() -> None:
    op.drop_table("purchases")
    op.drop_table("products")
    op.drop_table("categories")
