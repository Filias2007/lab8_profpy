"""Integration tests: raw DB-API (sqlite3) functions on the test database."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from shop.dbapi import (
    find_products_by_category,
    purchase_product_dbapi,
    search_products,
)
from shop.exceptions import InsufficientStockError, NotFoundError
from shop.models import Category, Product
from shop.repositories import ProductRepository


def _count_rows(db_path: Path, table: str) -> int:
    with closing(sqlite3.connect(db_path)) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_find_products_by_category(
    db_path: Path, electronics: Category, laptop: Product, mouse: Product, novel: Product
) -> None:
    rows = find_products_by_category(str(db_path), "Electronics")

    assert rows == [("Laptop", 1000.0, 5), ("Mouse", 25.0, 20)]


def test_find_products_in_unknown_category_is_empty(
    db_path: Path, laptop: Product
) -> None:
    assert find_products_by_category(str(db_path), "Unknown") == []


def test_parameterized_query_is_safe_from_sql_injection(
    db_path: Path, laptop: Product
) -> None:
    malicious = "Electronics' OR '1'='1"

    assert find_products_by_category(str(db_path), malicious) == []
    # the table is still there and untouched
    assert _count_rows(db_path, "products") == 1


def test_search_products_with_filters(
    db_path: Path, laptop: Product, mouse: Product, novel: Product
) -> None:
    cheap = search_products(str(db_path), max_price=30.0)
    in_books = search_products(str(db_path), category_name="Books")
    by_name = search_products(str(db_path), name_part="LAP")
    combined = search_products(
        str(db_path), category_name="Electronics", min_price=100.0
    )

    assert [row[0] for row in cheap] == ["Mouse", "Novel"]
    assert [row[0] for row in in_books] == ["Novel"]
    assert [row[0] for row in by_name] == ["Laptop"]
    assert [row[0] for row in combined] == ["Laptop"]


def test_search_products_without_filters_returns_everything(
    db_path: Path, laptop: Product, mouse: Product
) -> None:
    assert len(search_products(str(db_path))) == 2


def test_purchase_product_dbapi_commit(
    db_path: Path, session: Session, product_repo: ProductRepository, laptop: Product
) -> None:
    total = purchase_product_dbapi(str(db_path), laptop.id, 2)

    assert total == pytest.approx(2000.0)
    session.expire_all()
    reloaded = product_repo.get_by_id(laptop.id)
    assert reloaded is not None
    assert reloaded.quantity == 3
    assert _count_rows(db_path, "purchases") == 1


def test_purchase_product_dbapi_rollback_on_insufficient_stock(
    db_path: Path, session: Session, product_repo: ProductRepository, laptop: Product
) -> None:
    with pytest.raises(InsufficientStockError):
        purchase_product_dbapi(str(db_path), laptop.id, 100)

    session.expire_all()
    reloaded = product_repo.get_by_id(laptop.id)
    assert reloaded is not None
    assert reloaded.quantity == 5
    assert _count_rows(db_path, "purchases") == 0


def test_purchase_product_dbapi_unknown_product(db_path: Path, laptop: Product) -> None:
    with pytest.raises(NotFoundError):
        purchase_product_dbapi(str(db_path), 999_999, 1)
