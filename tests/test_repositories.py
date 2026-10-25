"""Integration tests: Repository + SQLAlchemy + SQLite (CRUD, filters, paging)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from shop.models import Category, Product
from shop.repositories import CategoryRepository, ProductRepository


# ---------------------------------------------------------------- Create
def test_add_category(category_repo: CategoryRepository) -> None:
    category = category_repo.add("Electronics")

    assert category.id is not None
    assert category.name == "Electronics"


def test_add_product(product_repo: ProductRepository, electronics: Category) -> None:
    saved = product_repo.add(
        Product(
            name="Laptop",
            price=1000.0,
            quantity=5,
            description="15-inch",
            category_id=electronics.id,
        )
    )

    assert saved.id is not None
    assert saved.name == "Laptop"
    assert saved.price == 1000.0
    assert saved.description == "15-inch"
    assert saved.category.name == "Electronics"


# ------------------------------------------------------------------ Read
def test_get_product_by_id(product_repo: ProductRepository, laptop: Product) -> None:
    loaded = product_repo.get_by_id(laptop.id)

    assert loaded is not None
    assert loaded.name == "Laptop"


def test_get_product_by_id_returns_none_for_unknown_id(
    product_repo: ProductRepository,
) -> None:
    assert product_repo.get_by_id(999_999) is None


def test_get_category_by_name(
    category_repo: CategoryRepository, electronics: Category
) -> None:
    loaded = category_repo.get_by_name("Electronics")

    assert loaded is not None
    assert loaded.id == electronics.id
    assert category_repo.get_by_name("Unknown") is None


def test_get_all_categories_sorted_by_name(
    category_repo: CategoryRepository, electronics: Category, books: Category
) -> None:
    names = [category.name for category in category_repo.get_all()]

    assert names == ["Books", "Electronics"]


def test_get_all_products_with_sorting(
    product_repo: ProductRepository,
    laptop: Product,
    mouse: Product,
    novel: Product,
) -> None:
    by_price_desc = product_repo.get_all(sort_by="price", descending=True)
    by_name = product_repo.get_all(sort_by="name")

    assert [p.name for p in by_price_desc] == ["Laptop", "Mouse", "Novel"]
    assert [p.name for p in by_name] == ["Laptop", "Mouse", "Novel"]


def test_get_all_rejects_unknown_sort_column(product_repo: ProductRepository) -> None:
    with pytest.raises(ValueError):
        product_repo.get_all(sort_by="password")


def test_find_product_by_name_is_case_insensitive(
    product_repo: ProductRepository, laptop: Product, mouse: Product
) -> None:
    found = product_repo.find_by_name("LAP")

    assert [p.name for p in found] == ["Laptop"]
    assert product_repo.find_by_name("nothing") == []


def test_filter_by_category(
    product_repo: ProductRepository,
    electronics: Category,
    books: Category,
    laptop: Product,
    mouse: Product,
    novel: Product,
) -> None:
    electronic_items = product_repo.filter_by_category(electronics.id)
    book_items = product_repo.filter_by_category(books.id)

    assert [p.name for p in electronic_items] == ["Laptop", "Mouse"]
    assert [p.name for p in book_items] == ["Novel"]


def test_most_expensive_product(
    product_repo: ProductRepository, laptop: Product, mouse: Product, novel: Product
) -> None:
    best = product_repo.most_expensive()

    assert best is not None
    assert best.name == "Laptop"


def test_most_expensive_product_of_empty_catalog(
    product_repo: ProductRepository,
) -> None:
    assert product_repo.most_expensive() is None


def test_pagination(
    product_repo: ProductRepository, electronics: Category
) -> None:
    for index in range(1, 6):
        product_repo.add(
            Product(
                name=f"Item {index}",
                price=float(index * 10),
                quantity=1,
                category_id=electronics.id,
            )
        )

    first_page = product_repo.get_page(1, 2, sort_by="price", descending=True)
    last_page = product_repo.get_page(3, 2, sort_by="price", descending=True)

    assert product_repo.count() == 5
    assert [p.name for p in first_page] == ["Item 5", "Item 4"]
    assert [p.name for p in last_page] == ["Item 1"]


def test_pagination_rejects_invalid_arguments(
    product_repo: ProductRepository,
) -> None:
    with pytest.raises(ValueError):
        product_repo.get_page(0, 10)
    with pytest.raises(ValueError):
        product_repo.get_page(1, 0)


def test_category_products_relationship(
    session: Session, electronics: Category, laptop: Product, mouse: Product
) -> None:
    session.refresh(electronics)

    assert {p.name for p in electronics.products} == {"Laptop", "Mouse"}
    assert laptop.category.id == electronics.id


# ---------------------------------------------------------------- Update
def test_update_price(product_repo: ProductRepository, laptop: Product) -> None:
    updated = product_repo.update_price(laptop.id, 899.0)

    assert updated is not None
    assert updated.price == 899.0


def test_update_quantity(product_repo: ProductRepository, laptop: Product) -> None:
    updated = product_repo.update_quantity(laptop.id, 42)

    assert updated is not None
    assert updated.quantity == 42


def test_update_description(product_repo: ProductRepository, laptop: Product) -> None:
    updated = product_repo.update_description(laptop.id, "Gaming laptop")

    assert updated is not None
    assert updated.description == "Gaming laptop"


def test_update_unknown_product_returns_none(
    product_repo: ProductRepository,
) -> None:
    assert product_repo.update_price(999_999, 10.0) is None
    assert product_repo.update_quantity(999_999, 1) is None


def test_rename_category(
    category_repo: CategoryRepository, electronics: Category
) -> None:
    renamed = category_repo.rename(electronics.id, "Gadgets")

    assert renamed is not None
    assert renamed.name == "Gadgets"


# ---------------------------------------------------------------- Delete
def test_delete_product(product_repo: ProductRepository, laptop: Product) -> None:
    product_id = laptop.id

    assert product_repo.delete(product_id) is True
    assert product_repo.get_by_id(product_id) is None


def test_delete_unknown_product_returns_false(
    product_repo: ProductRepository,
) -> None:
    assert product_repo.delete(999_999) is False


def test_delete_category_deletes_its_products(
    category_repo: CategoryRepository,
    product_repo: ProductRepository,
    electronics: Category,
    laptop: Product,
    mouse: Product,
    novel: Product,
) -> None:
    assert category_repo.delete(electronics.id) is True

    remaining = [p.name for p in product_repo.get_all()]
    assert remaining == ["Novel"]
