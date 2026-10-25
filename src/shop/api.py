"""REST API of the online shop (FastAPI)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from shop.dependencies import get_session
from shop.exceptions import (
    DuplicateCategoryError,
    InsufficientStockError,
    InvalidProductError,
    NotFoundError,
)
from shop.external_api import FetchSettings, fetch_many_products
from shop.models import Product
from shop.repositories import CategoryRepository, ProductRepository
from shop.schemas import (
    BatchRequest,
    BatchResponse,
    CategoryCreate,
    CategoryResponse,
    ErrorResponse,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
    PurchaseRequest,
    PurchaseResponse,
    StockValueResponse,
)
from shop.services import ShopService, purchase_product

# ===== Application, error handlers, root =====
app = FastAPI(
    title="Online Shop API",
    version="1.0.0",
    description=(
        "Asynchronous REST API of the online shop (Lab 8, variant 3). "
        "Works with the persistence layer from Lab 7."
    ),
    openapi_tags=[
        {"name": "root", "description": "Service status"},
        {"name": "categories", "description": "Product categories"},
        {"name": "products", "description": "CRUD, search, filtering and purchase of products"},
        {"name": "statistics", "description": "Aggregated data"},
        {"name": "async", "description": "Concurrent operations: Task, gather, Semaphore, HTTPX"},
    ],
)


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(DuplicateCategoryError)
async def duplicate_handler(request: Request, exc: DuplicateCategoryError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(InsufficientStockError)
async def insufficient_stock_handler(
    request: Request, exc: InsufficientStockError
) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(InvalidProductError)
async def invalid_product_handler(request: Request, exc: InvalidProductError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)}
    )


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {"message": "Shop API is running"}


# ===== REST endpoints =====
SessionDep = Annotated[Session, Depends(get_session)]
ProductId = Annotated[int, Path(gt=0, description="Product id")]
CategoryId = Annotated[int, Path(gt=0, description="Category id")]

ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Entity not found"},
    409: {"model": ErrorResponse, "description": "Conflict"},
}


# ---- categories ---------------------------------------------------------
@app.get("/categories", response_model=list[CategoryResponse], tags=["categories"])
async def list_categories(session: SessionDep) -> list[CategoryResponse]:
    categories = CategoryRepository(session).get_all()
    return [CategoryResponse.model_validate(item) for item in categories]


@app.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["categories"],
    responses={409: ERROR_RESPONSES[409]},
)
async def create_category(data: CategoryCreate, session: SessionDep) -> CategoryResponse:
    category = CategoryRepository(session).add(data.name)
    return CategoryResponse.model_validate(category)


@app.get(
    "/categories/{category_id}/products",
    response_model=list[ProductResponse],
    tags=["categories"],
    responses={404: ERROR_RESPONSES[404]},
)
async def get_category_products(
    category_id: CategoryId, session: SessionDep
) -> list[ProductResponse]:
    if CategoryRepository(session).get_by_id(category_id) is None:
        raise NotFoundError(f"Category {category_id} not found")
    products = ProductRepository(session).filter_by_category(category_id)
    return [ProductResponse.model_validate(item) for item in products]


# ---- products: read -----------------------------------------------------
@app.get("/products", response_model=ProductListResponse, tags=["products"])
async def list_products(
    session: SessionDep,
    category_id: Annotated[int | None, Query(gt=0, description="Filter by category")] = None,
    q: Annotated[
        str | None,
        Query(min_length=1, max_length=100, description="Search in the product name"),
    ] = None,
    min_price: Annotated[float | None, Query(ge=0)] = None,
    max_price: Annotated[float | None, Query(ge=0)] = None,
    sort_by: Annotated[Literal["id", "name", "price", "quantity"], Query()] = "id",
    descending: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductListResponse:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_price must not be greater than max_price",
        )
    products, total = ProductRepository(session).search(
        category_id=category_id,
        name=q,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        descending=descending,
        page=page,
        page_size=page_size,
    )
    return ProductListResponse(
        items=[ProductResponse.model_validate(item) for item in products],
        total=total,
        page=page,
        page_size=page_size,
    )


# NB: static paths must be declared before "/products/{product_id}".
@app.get(
    "/products/most-expensive",
    response_model=ProductResponse,
    tags=["products"],
    responses={404: ERROR_RESPONSES[404]},
)
async def get_most_expensive_product(session: SessionDep) -> ProductResponse:
    product = ProductRepository(session).most_expensive()
    if product is None:
        raise NotFoundError("The catalog is empty")
    return ProductResponse.model_validate(product)


@app.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    tags=["products"],
    responses={404: ERROR_RESPONSES[404]},
)
async def get_product(product_id: ProductId, session: SessionDep) -> ProductResponse:
    product = ProductRepository(session).get_by_id(product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return ProductResponse.model_validate(product)


# ---- products: create / update / delete ---------------------------------
@app.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["products"],
    responses={404: ERROR_RESPONSES[404]},
)
async def create_product(data: ProductCreate, session: SessionDep) -> ProductResponse:
    if CategoryRepository(session).get_by_id(data.category_id) is None:
        raise NotFoundError(f"Category {data.category_id} not found")
    product = ProductRepository(session).add(Product(**data.model_dump()))
    return ProductResponse.model_validate(product)


@app.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    tags=["products"],
    responses={404: ERROR_RESPONSES[404]},
)
async def update_product(
    product_id: ProductId, data: ProductUpdate, session: SessionDep
) -> ProductResponse:
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )
    repository = ProductRepository(session)
    if repository.get_by_id(product_id) is None:
        raise NotFoundError(f"Product {product_id} not found")
    new_category_id = changes.get("category_id")
    if new_category_id is not None and CategoryRepository(session).get_by_id(
        int(new_category_id)
    ) is None:
        raise NotFoundError(f"Category {new_category_id} not found")
    product = repository.update(product_id, changes)
    if product is None:  # deleted between the two calls
        raise NotFoundError(f"Product {product_id} not found")
    return ProductResponse.model_validate(product)


@app.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["products"],
    responses={404: ERROR_RESPONSES[404]},
)
async def delete_product(product_id: ProductId, session: SessionDep) -> None:
    if not ProductRepository(session).delete(product_id):
        raise NotFoundError(f"Product {product_id} not found")


# ---- purchase (transaction from Lab 7) ----------------------------------
@app.post(
    "/products/{product_id}/purchase",
    response_model=PurchaseResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["products"],
    responses={404: ERROR_RESPONSES[404], 409: ERROR_RESPONSES[409]},
)
async def purchase(
    product_id: ProductId, data: PurchaseRequest, session: SessionDep
) -> PurchaseResponse:
    """Check stock, decrease quantity and record the purchase in ONE transaction.

    Not enough stock -> 409 and rollback; unknown product -> 404.
    """
    result = purchase_product(session, product_id, data.quantity)
    return PurchaseResponse.model_validate(result)


# ---- statistics ---------------------------------------------------------
@app.get("/stock/value", response_model=StockValueResponse, tags=["statistics"])
async def get_stock_value(session: SessionDep) -> StockValueResponse:
    return StockValueResponse(total_value=ShopService(session).get_stock_value())


# ===== Concurrent operations (Task, gather, Semaphore, HTTPX) =====
INTERNAL_BASE_URL = "http://shop.internal"


def get_fetch_settings() -> FetchSettings:
    """Dependency: limits of the asynchronous client (overridden in tests)."""
    return FetchSettings()


@app.post(
    "/products/batch",
    response_model=BatchResponse,
    tags=["async"],
    responses={502: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)
async def batch_products(
    data: BatchRequest,
    settings: Annotated[FetchSettings, Depends(get_fetch_settings)],
) -> BatchResponse:
    """Load several products concurrently through HTTPX.

    The API calls itself over HTTP (in-process ASGI transport): the requests are
    wrapped into Tasks, limited by a Semaphore, repeated on temporary errors
    and the whole operation is limited by a timeout.
    """
    product_ids = list(dict.fromkeys(data.product_ids))  # unique, keep order
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=INTERNAL_BASE_URL,
        timeout=settings.request_timeout,
    ) as client:
        try:
            results = await asyncio.wait_for(
                fetch_many_products(client, product_ids, settings=settings),
                timeout=settings.batch_timeout,
            )
        except asyncio.TimeoutError as error:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Batch operation timed out",
            ) from error
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Request to the product service failed: {error}",
            ) from error

    found = [ProductResponse.model_validate(item) for item in results if item is not None]
    not_found = [
        product_id for product_id, item in zip(product_ids, results) if item is None
    ]
    return BatchResponse(found=found, not_found=not_found)
