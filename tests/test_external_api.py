"""Tests of the asynchronous HTTP client with a mocked external service (httpx.MockTransport)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx
import pytest

from shop.external_api import (
    FetchSettings,
    fetch_many_products,
    fetch_product,
    get_json_with_retry,
)

Handler = Callable[[httpx.Request], httpx.Response]


def make_client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mock-shop"
    )


def product_json(product_id: int) -> dict[str, object]:
    return {
        "id": product_id,
        "name": f"Item {product_id}",
        "price": 10.0,
        "quantity": 1,
        "description": None,
        "category_id": 1,
    }


# ----------------------------------------------------------------- HTTPX
async def test_fetch_product_returns_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/products/7"
        return httpx.Response(200, json=product_json(7))

    async with make_client(handler) as client:
        result = await fetch_product(client, 7)

    assert result is not None
    assert result["name"] == "Item 7"


async def test_fetch_product_returns_none_for_404_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"detail": "Product not found"})

    async with make_client(handler) as client:
        result = await fetch_product(client, 1, base_delay=0)

    assert result is None
    assert calls == 1


# ----------------------------------------------------------------- retry
async def test_retry_succeeds_after_temporary_errors() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=product_json(1))

    async with make_client(handler) as client:
        result = await get_json_with_retry(client, "/products/1", attempts=3, base_delay=0)

    assert result is not None
    assert calls == 3


async def test_retry_gives_up_after_all_attempts() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async with make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await get_json_with_retry(client, "/products/1", attempts=3, base_delay=0)

    assert calls == 3


async def test_retry_repeats_network_errors() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=product_json(1))

    async with make_client(handler) as client:
        result = await get_json_with_retry(client, "/products/1", attempts=3, base_delay=0)

    assert result is not None
    assert calls == 3


async def test_retry_does_not_repeat_client_errors() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    async with make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await get_json_with_retry(client, "/products/1", attempts=3, base_delay=0)

    assert calls == 1


async def test_retry_rejects_invalid_attempts() -> None:
    async with make_client(lambda request: httpx.Response(200, json={})) as client:
        with pytest.raises(ValueError):
            await get_json_with_retry(client, "/x", attempts=0)


async def test_exponential_backoff_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async with make_client(lambda request: httpx.Response(503)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await get_json_with_retry(client, "/x", attempts=4, base_delay=0.5)

    assert delays == [0.5, 1.0, 2.0]


# ---------------------------------------------- Task + gather + Semaphore
async def test_fetch_many_products_keeps_order_and_marks_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        product_id = int(request.url.path.rsplit("/", 1)[1])
        if product_id == 3:
            return httpx.Response(404, json={"detail": "Product not found"})
        return httpx.Response(200, json=product_json(product_id))

    async with make_client(handler) as client:
        results = await fetch_many_products(client, [5, 3, 1, 2])

    assert [None if item is None else item["id"] for item in results] == [5, None, 1, 2]


async def test_semaphore_limits_concurrency() -> None:
    running = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        product_id = int(request.url.path.rsplit("/", 1)[1])
        return httpx.Response(200, json=product_json(product_id))

    async with make_client(handler) as client:
        results = await fetch_many_products(
            client, list(range(1, 13)), settings=FetchSettings(concurrency=3)
        )

    assert len(results) == 12
    assert peak == 3


async def test_requests_run_in_parallel() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.1)
        return httpx.Response(200, json=product_json(1))

    loop = asyncio.get_running_loop()
    started = loop.time()
    async with make_client(handler) as client:
        await fetch_many_products(client, [1, 2, 3, 4, 5], settings=FetchSettings(concurrency=5))
    elapsed = loop.time() - started

    assert elapsed < 0.4  # sequentially it would take at least 0.5 s


async def test_batch_timeout_cancels_pending_tasks() -> None:
    cancelled = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cancelled
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled += 1
            raise
        return httpx.Response(200, json=product_json(1))

    async with make_client(handler) as client:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                fetch_many_products(client, [1, 2, 3], settings=FetchSettings(concurrency=3)),
                timeout=0.05,
            )

    assert cancelled == 3


async def test_error_in_one_task_cancels_the_others() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        product_id = int(request.url.path.rsplit("/", 1)[1])
        if product_id == 1:
            return httpx.Response(400)
        await asyncio.sleep(5)
        return httpx.Response(200, json=product_json(product_id))

    async with make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await asyncio.wait_for(
                fetch_many_products(client, [1, 2, 3], settings=FetchSettings(base_delay=0)),
                timeout=2,
            )
