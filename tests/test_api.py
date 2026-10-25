"""API integration tests: FastAPI + Pydantic + Service/Repository layers + test SQLite DB."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from shop import api as api_module
from shop.api import app, get_fetch_settings
from shop.external_api import FetchSettings
from shop.models import Category, Product


# ------------------------------------------------------------------ root
def test_root(api_client: TestClient) -> None:
    response = api_client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Shop API is running"}


def test_openapi_documentation_is_available(api_client: TestClient) -> None:
    response = api_client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/products" in paths
    assert "/products/{product_id}/purchase" in paths
    assert api_client.get("/docs").status_code == 200


# ------------------------------------------------------------ categories
def test_create_category(api_client: TestClient) -> None:
    response = api_client.post("/categories", json={"name": "Electronics"})

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Electronics"
    assert data["id"] > 0


def test_create_duplicate_category_returns_409(api_client: TestClient) -> None:
    api_client.post("/categories", json={"name": "Books"})

    response = api_client.post("/categories", json={"name": "Books"})

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_create_category_with_empty_name_returns_422(api_client: TestClient) -> None:
    response = api_client.post("/categories", json={"name": "   "})

    assert response.status_code == 422


def test_list_categories(
    api_client: TestClient, electronics: Category, books: Category
) -> None:
    response = api_client.get("/categories")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Books", "Electronics"]


def test_get_category_products(
    api_client: TestClient,
    electronics: Category,
    laptop: Product,
    mouse: Product,
    novel: Product,
) -> None:
    response = api_client.get(f"/categories/{electronics.id}/products")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Laptop", "Mouse"]


def test_get_products_of_unknown_category_returns_404(api_client: TestClient) -> None:
    response = api_client.get("/categories/999/products")

    assert response.status_code == 404


# ----------------------------------------------------------- POST /products
def test_create_product(api_client: TestClient, electronics: Category) -> None:
    response = api_client.post(
        "/products",
        json={
            "name": "Keyboard",
            "price": 60.0,
            "quantity": 15,
            "description": "Mechanical",
            "category_id": electronics.id,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] > 0
    assert data["name"] == "Keyboard"
    assert data["price"] == 60.0
    assert data["description"] == "Mechanical"
    assert data["category_id"] == electronics.id


def test_create_product_with_unknown_category_returns_404(api_client: TestClient) -> None:
    response = api_client.post(
        "/products",
        json={"name": "Orphan", "price": 1.0, "quantity": 1, "category_id": 999},
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Bad", "price": -1.0, "quantity": 1, "category_id": 1},
        {"name": "Bad", "price": 1.0, "quantity": -5, "category_id": 1},
        {"name": "", "price": 1.0, "quantity": 1, "category_id": 1},
        {"name": "Bad", "price": 1.0, "quantity": 1, "category_id": 0},
        {"name": "Bad", "price": "free", "quantity": 1, "category_id": 1},
        {"price": 1.0, "quantity": 1, "category_id": 1},
    ],
)
def test_create_product_validation_errors_return_422(
    api_client: TestClient, payload: dict[str, Any]
) -> None:
    response = api_client.post("/products", json=payload)

    assert response.status_code == 422


# ------------------------------------------------------------- GET /products
def test_list_products(
    api_client: TestClient, laptop: Product, mouse: Product, novel: Product
) -> None:
    response = api_client.get("/products")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert [item["name"] for item in data["items"]] == ["Laptop", "Mouse", "Novel"]


def test_list_products_of_empty_catalog(api_client: TestClient) -> None:
    response = api_client.get("/products")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_list_products_filter_by_category(
    api_client: TestClient,
    books: Category,
    laptop: Product,
    novel: Product,
) -> None:
    response = api_client.get("/products", params={"category_id": books.id})

    assert [item["name"] for item in response.json()["items"]] == ["Novel"]


def test_list_products_search_by_name(
    api_client: TestClient, laptop: Product, mouse: Product
) -> None:
    response = api_client.get("/products", params={"q": "LAP"})

    assert [item["name"] for item in response.json()["items"]] == ["Laptop"]


def test_list_products_price_range(
    api_client: TestClient, laptop: Product, mouse: Product, novel: Product
) -> None:
    response = api_client.get("/products", params={"min_price": 20, "max_price": 100})

    assert [item["name"] for item in response.json()["items"]] == ["Mouse"]


def test_list_products_sorting_and_pagination(
    api_client: TestClient, laptop: Product, mouse: Product, novel: Product
) -> None:
    response = api_client.get(
        "/products",
        params={"sort_by": "price", "descending": True, "page": 2, "page_size": 2},
    )

    data = response.json()
    assert data["total"] == 3
    assert data["page"] == 2
    assert [item["name"] for item in data["items"]] == ["Novel"]


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 1000},
        {"sort_by": "password"},
        {"min_price": -1},
        {"min_price": 100, "max_price": 10},
    ],
)
def test_list_products_invalid_query_returns_422(
    api_client: TestClient, params: dict[str, Any]
) -> None:
    response = api_client.get("/products", params=params)

    assert response.status_code == 422


# ----------------------------------------------------- GET /products/{id}
def test_get_product(api_client: TestClient, laptop: Product) -> None:
    response = api_client.get(f"/products/{laptop.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Laptop"


def test_get_unknown_product_returns_404(api_client: TestClient) -> None:
    response = api_client.get("/products/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found"}


def test_get_product_with_invalid_id_returns_422(api_client: TestClient) -> None:
    assert api_client.get("/products/abc").status_code == 422
    assert api_client.get("/products/0").status_code == 422


def test_get_most_expensive_product(
    api_client: TestClient, laptop: Product, mouse: Product
) -> None:
    response = api_client.get("/products/most-expensive")

    assert response.status_code == 200
    assert response.json()["name"] == "Laptop"


def test_most_expensive_product_of_empty_catalog_returns_404(
    api_client: TestClient,
) -> None:
    assert api_client.get("/products/most-expensive").status_code == 404


# ---------------------------------------------------- PATCH /products/{id}
def test_patch_price(api_client: TestClient, laptop: Product) -> None:
    response = api_client.patch(f"/products/{laptop.id}", json={"price": 899.0})

    assert response.status_code == 200
    data = response.json()
    assert data["price"] == 899.0
    assert data["quantity"] == 5  # other fields are untouched
    assert api_client.get(f"/products/{laptop.id}").json()["price"] == 899.0


def test_patch_quantity_and_description(api_client: TestClient, laptop: Product) -> None:
    response = api_client.patch(
        f"/products/{laptop.id}", json={"quantity": 42, "description": "Gaming"}
    )

    assert response.status_code == 200
    assert response.json()["quantity"] == 42
    assert response.json()["description"] == "Gaming"


def test_patch_move_to_another_category(
    api_client: TestClient, laptop: Product, books: Category
) -> None:
    response = api_client.patch(f"/products/{laptop.id}", json={"category_id": books.id})

    assert response.status_code == 200
    assert response.json()["category_id"] == books.id


def test_patch_unknown_product_returns_404(api_client: TestClient) -> None:
    assert api_client.patch("/products/999", json={"price": 1.0}).status_code == 404


def test_patch_unknown_category_returns_404(api_client: TestClient, laptop: Product) -> None:
    response = api_client.patch(f"/products/{laptop.id}", json={"category_id": 999})

    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [{}, {"price": -5}, {"quantity": -1}, {"name": None}, {"price": None}],
)
def test_patch_invalid_body_returns_422(
    api_client: TestClient, laptop: Product, payload: dict[str, Any]
) -> None:
    response = api_client.patch(f"/products/{laptop.id}", json=payload)

    assert response.status_code == 422
    assert api_client.get(f"/products/{laptop.id}").json()["price"] == 1000.0


# --------------------------------------------------- DELETE /products/{id}
def test_delete_product(api_client: TestClient, laptop: Product) -> None:
    response = api_client.delete(f"/products/{laptop.id}")

    assert response.status_code == 204
    assert response.content == b""
    assert api_client.get(f"/products/{laptop.id}").status_code == 404


def test_delete_unknown_product_returns_404(api_client: TestClient) -> None:
    assert api_client.delete("/products/999").status_code == 404


# ---------------------------------------------------------- stock value
def test_stock_value(
    api_client: TestClient, laptop: Product, mouse: Product, novel: Product
) -> None:
    response = api_client.get("/stock/value")

    assert response.status_code == 200
    assert response.json()["total_value"] == pytest.approx(5655.0)


def test_stock_value_of_empty_catalog(api_client: TestClient) -> None:
    assert api_client.get("/stock/value").json()["total_value"] == 0.0


# ------------------------------------------------- POST /products/{id}/purchase
def test_purchase_success(api_client: TestClient, laptop: Product) -> None:
    response = api_client.post(f"/products/{laptop.id}/purchase", json={"quantity": 2})

    assert response.status_code == 201
    data = response.json()
    assert data["product_id"] == laptop.id
    assert data["quantity"] == 2
    assert data["total_price"] == pytest.approx(2000.0)
    assert api_client.get(f"/products/{laptop.id}").json()["quantity"] == 3


def test_purchase_insufficient_stock_returns_409_and_rolls_back(
    api_client: TestClient, laptop: Product
) -> None:
    response = api_client.post(f"/products/{laptop.id}/purchase", json={"quantity": 6})

    assert response.status_code == 409
    assert "Not enough stock" in response.json()["detail"]
    assert api_client.get(f"/products/{laptop.id}").json()["quantity"] == 5
    assert api_client.get("/stock/value").json()["total_value"] == pytest.approx(5000.0)


def test_purchase_unknown_product_returns_404(api_client: TestClient) -> None:
    response = api_client.post("/products/999/purchase", json={"quantity": 1})

    assert response.status_code == 404


@pytest.mark.parametrize("quantity", [0, -1, "two"])
def test_purchase_invalid_quantity_returns_422(
    api_client: TestClient, laptop: Product, quantity: object
) -> None:
    response = api_client.post(
        f"/products/{laptop.id}/purchase", json={"quantity": quantity}
    )

    assert response.status_code == 422


# ------------------------------------------------------ POST /products/batch
def test_batch_products(
    api_client: TestClient, laptop: Product, mouse: Product, novel: Product
) -> None:
    response = api_client.post(
        "/products/batch",
        json={"product_ids": [novel.id, laptop.id, 999, laptop.id]},
    )

    assert response.status_code == 200
    data = response.json()
    assert [item["name"] for item in data["found"]] == ["Novel", "Laptop"]
    assert data["not_found"] == [999]


@pytest.mark.parametrize(
    "payload",
    [{"product_ids": []}, {"product_ids": [0]}, {"product_ids": ["x"]}, {}],
)
def test_batch_invalid_body_returns_422(
    api_client: TestClient, payload: dict[str, Any]
) -> None:
    assert api_client.post("/products/batch", json=payload).status_code == 422


def test_batch_timeout_returns_504(
    api_client: TestClient, laptop: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def very_slow_fetch(*args: Any, **kwargs: Any) -> list[Any]:
        await asyncio.sleep(5)
        return []

    monkeypatch.setattr(api_module, "fetch_many_products", very_slow_fetch)
    app.dependency_overrides[get_fetch_settings] = lambda: FetchSettings(batch_timeout=0.05)

    response = api_client.post("/products/batch", json={"product_ids": [laptop.id]})

    assert response.status_code == 504
    assert response.json() == {"detail": "Batch operation timed out"}


def test_batch_upstream_error_returns_502(
    api_client: TestClient, laptop: Product, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_fetch(*args: Any, **kwargs: Any) -> list[Any]:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(api_module, "fetch_many_products", failing_fetch)

    response = api_client.post("/products/batch", json={"product_ids": [laptop.id]})

    assert response.status_code == 502


# ------------------------------------------------- asynchronous API tests
async def test_async_api_root(override_session: None) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200


async def test_async_parallel_requests(
    override_session: None, laptop: Product, mouse: Product, novel: Product
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(
            client.get(f"/products/{laptop.id}"),
            client.get(f"/products/{mouse.id}"),
            client.get(f"/products/{novel.id}"),
            client.get("/stock/value"),
        )

    assert [r.status_code for r in responses] == [200, 200, 200, 200]
    assert [r.json()["name"] for r in responses[:3]] == ["Laptop", "Mouse", "Novel"]
    assert responses[3].json()["total_value"] == pytest.approx(5655.0)
