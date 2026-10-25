"""Fixtures: a separate SQLite test database for every test."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from shop.api import app
from shop.database import create_db_engine, create_session_factory
from shop.dependencies import get_session
from shop.models import Base, Category, Product
from shop.repositories import (
    CategoryRepository,
    ProductRepository,
    PurchaseRepository,
)
from shop.services import ShopService


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Path of a temporary test database (never the production shop.db)."""
    return tmp_path / "test_shop.db"


@pytest.fixture
def engine(db_path: Path) -> Iterator[Engine]:
    test_engine = create_db_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    factory = create_session_factory(engine)
    with factory() as test_session:
        yield test_session


@pytest.fixture
def category_repo(session: Session) -> CategoryRepository:
    return CategoryRepository(session)


@pytest.fixture
def product_repo(session: Session) -> ProductRepository:
    return ProductRepository(session)


@pytest.fixture
def purchase_repo(session: Session) -> PurchaseRepository:
    return PurchaseRepository(session)


@pytest.fixture
def service(session: Session) -> ShopService:
    return ShopService(session)


@pytest.fixture
def electronics(category_repo: CategoryRepository) -> Category:
    return category_repo.add("Electronics")


@pytest.fixture
def books(category_repo: CategoryRepository) -> Category:
    return category_repo.add("Books")


@pytest.fixture
def laptop(product_repo: ProductRepository, electronics: Category) -> Product:
    return product_repo.add(
        Product(name="Laptop", price=1000.0, quantity=5, category_id=electronics.id)
    )


@pytest.fixture
def mouse(product_repo: ProductRepository, electronics: Category) -> Product:
    return product_repo.add(
        Product(name="Mouse", price=25.0, quantity=20, category_id=electronics.id)
    )


@pytest.fixture
def novel(product_repo: ProductRepository, books: Category) -> Product:
    return product_repo.add(
        Product(name="Novel", price=15.5, quantity=10, category_id=books.id)
    )


# ---------------------------------------------------------------- API
@pytest.fixture
def override_session(engine: Engine) -> Iterator[None]:
    """Make the API use the separate test database instead of shop.db."""
    factory = create_session_factory(engine)

    async def _get_test_session() -> AsyncGenerator[Session, None]:
        test_session = factory()
        try:
            yield test_session
        finally:
            test_session.close()

    app.dependency_overrides[get_session] = _get_test_session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def api_client(override_session: None) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
