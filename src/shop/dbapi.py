"""Python DB-API (sqlite3) without ORM: parameterized queries and a transaction."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from shop.exceptions import InsufficientStockError, NotFoundError


def _connect(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def find_products_by_category(
    database_path: str, category_name: str
) -> list[tuple[str, float, int]]:
    """Parameterized JOIN query: products of the category with the given name."""
    with closing(_connect(database_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT products.name, products.price, products.quantity
            FROM products
            JOIN categories
                ON products.category_id = categories.id
            WHERE categories.name = ?
            ORDER BY products.name
            """,
            (category_name,),
        )
        return cursor.fetchall()


def search_products(
    database_path: str,
    *,
    category_name: str | None = None,
    name_part: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> list[tuple[str, str, float, int]]:
    """Parameterized search/filtering. User values are passed only as '?' parameters."""
    conditions: list[str] = []
    parameters: list[object] = []
    if category_name is not None:
        conditions.append("categories.name = ?")
        parameters.append(category_name)
    if name_part is not None:
        conditions.append("products.name LIKE '%' || ? || '%'")
        parameters.append(name_part)
    if min_price is not None:
        conditions.append("products.price >= ?")
        parameters.append(min_price)
    if max_price is not None:
        conditions.append("products.price <= ?")
        parameters.append(max_price)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT products.name, categories.name, products.price, products.quantity
        FROM products
        JOIN categories ON products.category_id = categories.id
        {where_clause}
        ORDER BY products.name
    """
    with closing(_connect(database_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(query, parameters)
        return cursor.fetchall()


def purchase_product_dbapi(database_path: str, product_id: int, quantity: int) -> float:
    """The same purchase transaction as in services.py, but with explicit DB-API calls.

    Returns the total price of the purchase.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be a positive number")

    connection = _connect(database_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT price, quantity FROM products WHERE id = ?",
            (product_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise NotFoundError(f"Product {product_id} not found")
        price, available = row
        if available < quantity:
            raise InsufficientStockError(product_id, quantity, available)

        cursor.execute(
            "UPDATE products SET quantity = quantity - ? WHERE id = ? AND quantity >= ?",
            (quantity, product_id, quantity),
        )
        if cursor.rowcount != 1:
            raise InsufficientStockError(product_id, quantity, available)

        total_price = price * quantity
        cursor.execute(
            """
            INSERT INTO purchases (product_id, quantity, total_price, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                product_id,
                quantity,
                total_price,
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
            ),
        )
        connection.commit()
        return total_price
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
