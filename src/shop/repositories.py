"""Repository Pattern: the only place that talks to the database about entities."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shop.exceptions import DuplicateCategoryError, InvalidProductError
from shop.models import Category, Product, Purchase


class CategoryRepository:
    """CRUD operations for categories."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, name: str) -> Category:
        category = Category(name=name)
        self.session.add(category)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateCategoryError(name) from exc
        self.session.refresh(category)
        return category

    def get_by_id(self, category_id: int) -> Category | None:
        return self.session.get(Category, category_id)

    def get_by_name(self, name: str) -> Category | None:
        statement = select(Category).where(Category.name == name)
        return self.session.scalar(statement)

    def get_all(self) -> list[Category]:
        statement = select(Category).order_by(Category.name)
        return list(self.session.scalars(statement))

    def rename(self, category_id: int, new_name: str) -> Category | None:
        category = self.get_by_id(category_id)
        if category is None:
            return None
        category.name = new_name
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateCategoryError(new_name) from exc
        self.session.refresh(category)
        return category

    def delete(self, category_id: int) -> bool:
        """Delete a category together with its products (cascade)."""
        category = self.get_by_id(category_id)
        if category is None:
            return False
        self.session.delete(category)
        self.session.commit()
        return True


class ProductRepository:
    """CRUD, search, filtering, sorting and pagination for products."""

    _SORT_COLUMNS = {
        "id": Product.id,
        "name": Product.name,
        "price": Product.price,
        "quantity": Product.quantity,
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- helpers -------------------------------------------------------
    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise InvalidProductError(str(exc.orig)) from exc

    def _sort_column(self, sort_by: str):  # type: ignore[no-untyped-def]
        try:
            return self._SORT_COLUMNS[sort_by]
        except KeyError:
            allowed = ", ".join(sorted(self._SORT_COLUMNS))
            raise ValueError(f"Unknown sort column '{sort_by}'. Allowed: {allowed}")

    # ---- Create --------------------------------------------------------
    def add(self, product: Product) -> Product:
        self.session.add(product)
        self._commit()
        self.session.refresh(product)
        return product

    # ---- Read ----------------------------------------------------------
    def get_by_id(self, product_id: int) -> Product | None:
        return self.session.get(Product, product_id)

    def get_all(self, sort_by: str = "id", descending: bool = False) -> list[Product]:
        column = self._sort_column(sort_by)
        order = column.desc() if descending else column.asc()
        statement = select(Product).order_by(order, Product.id)
        return list(self.session.scalars(statement))

    def find_by_name(self, text: str) -> list[Product]:
        """Case-insensitive search of products by a part of the name."""
        statement = (
            select(Product)
            .where(func.lower(Product.name).contains(text.lower(), autoescape=True))
            .order_by(Product.name)
        )
        return list(self.session.scalars(statement))

    def filter_by_category(self, category_id: int) -> list[Product]:
        statement = (
            select(Product)
            .where(Product.category_id == category_id)
            .order_by(Product.name)
        )
        return list(self.session.scalars(statement))

    def most_expensive(self) -> Product | None:
        statement = select(Product).order_by(Product.price.desc(), Product.id).limit(1)
        return self.session.scalar(statement)

    def count(self) -> int:
        statement = select(func.count(Product.id))
        return int(self.session.scalar(statement) or 0)

    def get_page(
        self,
        page: int,
        page_size: int,
        sort_by: str = "id",
        descending: bool = False,
    ) -> list[Product]:
        """Pagination: page numbers start from 1."""
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive")
        column = self._sort_column(sort_by)
        order = column.desc() if descending else column.asc()
        statement = (
            select(Product)
            .order_by(order, Product.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return list(self.session.scalars(statement))

    def search(
        self,
        *,
        category_id: int | None = None,
        name: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        sort_by: str = "id",
        descending: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Product], int]:
        """Filtering + sorting + pagination. Returns (items of the page, total count)."""
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive")
        column = self._sort_column(sort_by)

        conditions = []
        if category_id is not None:
            conditions.append(Product.category_id == category_id)
        if name:
            conditions.append(
                func.lower(Product.name).contains(name.lower(), autoescape=True)
            )
        if min_price is not None:
            conditions.append(Product.price >= min_price)
        if max_price is not None:
            conditions.append(Product.price <= max_price)

        total_statement = select(func.count(Product.id)).where(*conditions)
        total = int(self.session.scalar(total_statement) or 0)

        order = column.desc() if descending else column.asc()
        statement = (
            select(Product)
            .where(*conditions)
            .order_by(order, Product.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return list(self.session.scalars(statement)), total

    # ---- Update --------------------------------------------------------
    _UPDATABLE_FIELDS = frozenset(
        {"name", "price", "quantity", "description", "category_id"}
    )

    def update(self, product_id: int, changes: dict[str, object]) -> Product | None:
        """Partial update (PATCH): only the given fields are changed."""
        unknown = set(changes) - self._UPDATABLE_FIELDS
        if unknown:
            raise ValueError(f"Unknown fields: {', '.join(sorted(unknown))}")
        product = self.get_by_id(product_id)
        if product is None:
            return None
        for field, value in changes.items():
            setattr(product, field, value)
        self._commit()
        self.session.refresh(product)
        return product

    def update_price(self, product_id: int, price: float) -> Product | None:
        product = self.get_by_id(product_id)
        if product is None:
            return None
        product.price = price
        self._commit()
        self.session.refresh(product)
        return product

    def update_quantity(self, product_id: int, quantity: int) -> Product | None:
        product = self.get_by_id(product_id)
        if product is None:
            return None
        product.quantity = quantity
        self._commit()
        self.session.refresh(product)
        return product

    def update_description(
        self, product_id: int, description: str | None
    ) -> Product | None:
        product = self.get_by_id(product_id)
        if product is None:
            return None
        product.description = description
        self._commit()
        self.session.refresh(product)
        return product

    # ---- Delete --------------------------------------------------------
    def delete(self, product_id: int) -> bool:
        product = self.get_by_id(product_id)
        if product is None:
            return False
        self.session.delete(product)
        self.session.commit()
        return True


class PurchaseRepository:
    """Read access to the history of purchase operations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_all(self) -> list[Purchase]:
        statement = select(Purchase).order_by(Purchase.id)
        return list(self.session.scalars(statement))

    def list_by_product(self, product_id: int) -> list[Purchase]:
        statement = (
            select(Purchase)
            .where(Purchase.product_id == product_id)
            .order_by(Purchase.id)
        )
        return list(self.session.scalars(statement))

    def count(self) -> int:
        statement = select(func.count(Purchase.id))
        return int(self.session.scalar(statement) or 0)
