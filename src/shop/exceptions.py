"""Domain exceptions of the online shop."""

from __future__ import annotations


class ShopError(Exception):
    """Base class for all shop-related errors."""


class NotFoundError(ShopError):
    """Raised when an entity with the requested id does not exist."""


class DuplicateCategoryError(ShopError):
    """Raised when a category with the same name already exists."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Category '{name}' already exists")
        self.name = name


class InvalidProductError(ShopError):
    """Raised when a product violates a database constraint."""


class InsufficientStockError(ShopError):
    """Raised when there are not enough items in stock for a purchase."""

    def __init__(self, product_id: int, requested: int, available: int) -> None:
        super().__init__(
            f"Not enough stock for product {product_id}: "
            f"requested {requested}, available {available}"
        )
        self.product_id = product_id
        self.requested = requested
        self.available = available
