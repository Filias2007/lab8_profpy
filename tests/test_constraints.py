"""Integration tests: UNIQUE, CHECK, FOREIGN KEY, IntegrityError and cascade delete."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shop.exceptions import DuplicateCategoryError, InvalidProductError
from shop.models import Category, Product
from shop.repositories import (
    CategoryRepository,
    ProductRepository,
    PurchaseRepository,
)
from shop.services import purchase_product


def test_category_name_must_be_unique(
    category_repo: CategoryRepository, electronics: Category
) -> None:
    with pytest.raises(DuplicateCategoryError):
        category_repo.add("Electronics")

    assert len(category_repo.get_all()) == 1


def test_rename_to_existing_name_is_rejected(
    category_repo: CategoryRepository, electronics: Category, books: Category
) -> None:
    with pytest.raises(DuplicateCategoryError):
        category_repo.rename(books.id, "Electronics")

    session_category = category_repo.get_by_id(books.id)
    assert session_category is not None
    assert session_category.name == "Books"


def test_negative_price_is_rejected(
    product_repo: ProductRepository, electronics: Category
) -> None:
    with pytest.raises(InvalidProductError):
        product_repo.add(
            Product(name="Bad", price=-1.0, quantity=1, category_id=electronics.id)
        )

    assert product_repo.count() == 0


def test_negative_quantity_is_rejected(
    product_repo: ProductRepository, electronics: Category
) -> None:
    with pytest.raises(InvalidProductError):
        product_repo.add(
            Product(name="Bad", price=1.0, quantity=-5, category_id=electronics.id)
        )

    assert product_repo.count() == 0


def test_update_price_to_negative_value_keeps_old_price(
    product_repo: ProductRepository, laptop: Product
) -> None:
    with pytest.raises(InvalidProductError):
        product_repo.update_price(laptop.id, -10.0)

    reloaded = product_repo.get_by_id(laptop.id)
    assert reloaded is not None
    assert reloaded.price == 1000.0


def test_product_with_unknown_category_violates_foreign_key(
    product_repo: ProductRepository,
) -> None:
    with pytest.raises(InvalidProductError):
        product_repo.add(
            Product(name="Orphan", price=1.0, quantity=1, category_id=999_999)
        )


def test_raw_integrity_error_from_database(
    session: Session, electronics: Category
) -> None:
    """Without the repository the database raises IntegrityError itself."""
    session.add(Product(name="Bad", price=-1.0, quantity=1, category_id=electronics.id))

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_delete_category_cascades_to_products_and_purchases(
    session: Session,
    category_repo: CategoryRepository,
    product_repo: ProductRepository,
    purchase_repo: PurchaseRepository,
    electronics: Category,
    laptop: Product,
) -> None:
    purchase_product(session, laptop.id, 1)
    assert purchase_repo.count() == 1

    category_repo.delete(electronics.id)

    assert product_repo.count() == 0
    assert purchase_repo.count() == 0
