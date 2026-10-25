"""Service layer: business logic on top of the persistence layer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shop.exceptions import InsufficientStockError, NotFoundError
from shop.models import Category, Product, Purchase


@dataclass(frozen=True, slots=True)
class CategoryStats:
    """Aggregated data about one category."""

    name: str
    product_count: int
    stock_value: float


class ShopService:
    """Aggregations and queries implemented with SQL functions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_stock_value(self) -> float:
        """SUM(price * quantity) over all products."""
        statement = select(
            func.coalesce(func.sum(Product.price * Product.quantity), 0.0)
        )
        return float(self.session.scalar(statement) or 0.0)

    def get_category_stock_value(self, category_id: int) -> float:
        statement = select(
            func.coalesce(func.sum(Product.price * Product.quantity), 0.0)
        ).where(Product.category_id == category_id)
        return float(self.session.scalar(statement) or 0.0)

    def get_average_price(self) -> float:
        """AVG(price); 0.0 for an empty catalog."""
        statement = select(func.avg(Product.price))
        result = self.session.scalar(statement)
        return 0.0 if result is None else float(result)

    def get_most_expensive_product(self) -> Product | None:
        statement = select(Product).order_by(Product.price.desc(), Product.id).limit(1)
        return self.session.scalar(statement)

    def get_category_stats(self) -> list[CategoryStats]:
        """JOIN + GROUP BY: number of products and stock value per category."""
        statement = (
            select(
                Category.name,
                func.count(Product.id),
                func.coalesce(func.sum(Product.price * Product.quantity), 0.0),
            )
            .select_from(Category)
            .outerjoin(Product, Product.category_id == Category.id)
            .group_by(Category.id, Category.name)
            .order_by(Category.name)
        )
        return [
            CategoryStats(name=row[0], product_count=int(row[1]), stock_value=float(row[2]))
            for row in self.session.execute(statement)
        ]


def _apply_purchase(session: Session, product_id: int, quantity: int) -> Purchase:
    """Check the stock, decrease quantity and record the operation (no commit)."""
    if quantity <= 0:
        raise ValueError("Quantity must be a positive number")
    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} not found")
    if product.quantity < quantity:
        raise InsufficientStockError(product_id, quantity, product.quantity)
    product.quantity -= quantity
    purchase = Purchase(
        product_id=product.id,
        quantity=quantity,
        total_price=product.price * quantity,
    )
    session.add(purchase)
    session.flush()  # send changes to the DB inside the still open transaction
    return purchase


def purchase_product(session: Session, product_id: int, quantity: int) -> Purchase:
    """Transaction: check stock, decrease quantity, record the purchase.

    Everything is committed together; on any error the whole transaction
    is rolled back (Atomicity).
    """
    try:
        purchase = _apply_purchase(session, product_id, quantity)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return purchase


def purchase_many(session: Session, items: Sequence[tuple[int, int]]) -> list[Purchase]:
    """Buy several products in ONE transaction: all items or nothing."""
    try:
        purchases = [
            _apply_purchase(session, product_id, quantity)
            for product_id, quantity in items
        ]
        session.commit()
    except Exception:
        session.rollback()
        raise
    return purchases
