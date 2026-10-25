"""Integration tests: service layer, SQL aggregates and transactions."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from shop.exceptions import InsufficientStockError, NotFoundError
from shop.models import Category, Product
from shop.repositories import (
    CategoryRepository,
    ProductRepository,
    PurchaseRepository,
)
from shop.services import ShopService, purchase_many, purchase_product


# ------------------------------------------------------------ aggregates
def test_stock_value(
    service: ShopService, laptop: Product, mouse: Product, novel: Product
) -> None:
    # 1000*5 + 25*20 + 15.5*10
    assert service.get_stock_value() == pytest.approx(5655.0)


def test_stock_value_of_empty_catalog_is_zero(service: ShopService) -> None:
    assert service.get_stock_value() == 0.0


def test_category_stock_value(
    service: ShopService,
    electronics: Category,
    books: Category,
    laptop: Product,
    mouse: Product,
    novel: Product,
) -> None:
    assert service.get_category_stock_value(electronics.id) == pytest.approx(5500.0)
    assert service.get_category_stock_value(books.id) == pytest.approx(155.0)


def test_average_price(
    service: ShopService, laptop: Product, mouse: Product, novel: Product
) -> None:
    assert service.get_average_price() == pytest.approx((1000.0 + 25.0 + 15.5) / 3)


def test_average_price_of_empty_catalog_is_zero(service: ShopService) -> None:
    assert service.get_average_price() == 0.0


def test_most_expensive_product(
    service: ShopService, laptop: Product, mouse: Product
) -> None:
    best = service.get_most_expensive_product()

    assert best is not None
    assert best.name == "Laptop"


def test_category_stats_group_by(
    service: ShopService,
    category_repo: CategoryRepository,
    electronics: Category,
    books: Category,
    laptop: Product,
    mouse: Product,
    novel: Product,
) -> None:
    category_repo.add("Empty")

    stats = {item.name: item for item in service.get_category_stats()}

    assert stats["Electronics"].product_count == 2
    assert stats["Electronics"].stock_value == pytest.approx(5500.0)
    assert stats["Books"].product_count == 1
    assert stats["Empty"].product_count == 0
    assert stats["Empty"].stock_value == 0.0


# ----------------------------------------------------------- transactions
def test_purchase_product_success(
    session: Session,
    product_repo: ProductRepository,
    purchase_repo: PurchaseRepository,
    laptop: Product,
) -> None:
    purchase = purchase_product(session, laptop.id, 2)

    assert purchase.id is not None
    assert purchase.quantity == 2
    assert purchase.total_price == pytest.approx(2000.0)
    session.expire_all()
    reloaded = product_repo.get_by_id(laptop.id)
    assert reloaded is not None
    assert reloaded.quantity == 3
    assert purchase_repo.count() == 1


def test_purchase_product_insufficient_stock_rolls_back(
    session: Session,
    product_repo: ProductRepository,
    purchase_repo: PurchaseRepository,
    laptop: Product,
) -> None:
    with pytest.raises(InsufficientStockError) as error:
        purchase_product(session, laptop.id, 6)

    assert error.value.available == 5
    session.refresh(laptop)
    assert laptop.quantity == 5
    assert purchase_repo.count() == 0


def test_purchase_product_unknown_product(session: Session) -> None:
    with pytest.raises(NotFoundError):
        purchase_product(session, 999_999, 1)


@pytest.mark.parametrize("quantity", [0, -3])
def test_purchase_product_rejects_non_positive_quantity(
    session: Session, laptop: Product, quantity: int
) -> None:
    with pytest.raises(ValueError):
        purchase_product(session, laptop.id, quantity)

    session.refresh(laptop)
    assert laptop.quantity == 5


def test_purchase_many_success(
    session: Session,
    purchase_repo: PurchaseRepository,
    laptop: Product,
    mouse: Product,
) -> None:
    purchases = purchase_many(session, [(laptop.id, 1), (mouse.id, 5)])

    assert len(purchases) == 2
    assert purchase_repo.count() == 2
    session.refresh(laptop)
    session.refresh(mouse)
    assert laptop.quantity == 4
    assert mouse.quantity == 15


def test_purchase_many_rolls_back_everything_on_error(
    session: Session,
    purchase_repo: PurchaseRepository,
    laptop: Product,
    mouse: Product,
) -> None:
    """The first item is valid, the second one fails: nothing may be saved (Atomicity)."""
    with pytest.raises(InsufficientStockError):
        purchase_many(session, [(laptop.id, 1), (mouse.id, 500)])

    session.refresh(laptop)
    session.refresh(mouse)
    assert laptop.quantity == 5
    assert mouse.quantity == 20
    assert purchase_repo.count() == 0
