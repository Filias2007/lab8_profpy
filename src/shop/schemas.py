"""Pydantic schemas: request bodies, responses and validation rules."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator


# ------------------------------------------------------------- categories
class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100, examples=["Electronics"])


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


# --------------------------------------------------------------- products
class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200, examples=["Laptop"])
    price: float = Field(ge=0, allow_inf_nan=False, examples=[1200.0])
    quantity: int = Field(ge=0, examples=[5])
    description: str | None = Field(default=None, max_length=2000)
    category_id: int = Field(gt=0, examples=[1])


class ProductUpdate(BaseModel):
    """PATCH body: every field is optional, but an explicit null is not allowed."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    quantity: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=2000)
    category_id: int | None = Field(default=None, gt=0)

    @field_validator("name", "price", "quantity", "category_id")
    @classmethod
    def _reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("must not be null")
        return value


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: float
    quantity: int
    description: str | None
    category_id: int


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int


# -------------------------------------------------------------- purchases
class PurchaseRequest(BaseModel):
    quantity: int = Field(gt=0, examples=[2])


class PurchaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    total_price: float
    created_at: datetime


# ------------------------------------------------------- statistics, batch
class StockValueResponse(BaseModel):
    total_value: float


class BatchRequest(BaseModel):
    product_ids: list[PositiveInt] = Field(min_length=1, max_length=100)


class BatchResponse(BaseModel):
    found: list[ProductResponse]
    not_found: list[int]


class ErrorResponse(BaseModel):
    """Structured error body returned by all error handlers."""

    detail: str
