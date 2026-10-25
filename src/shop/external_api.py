"""Asynchronous HTTP client: HTTPX + Task + gather + Semaphore + timeout + retry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

# Temporary failures are worth repeating; other 4xx errors are not.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class FetchSettings:
    """Configurable limits of the asynchronous client."""

    concurrency: int = 3  # Semaphore size: max simultaneous requests
    attempts: int = 3  # retry count (including the first attempt)
    base_delay: float = 0.2  # exponential backoff: base_delay * 2 ** (attempt - 1)
    request_timeout: float = 5.0  # timeout of one HTTP request (HTTPX)
    batch_timeout: float = 10.0  # timeout of the whole batch (asyncio.wait_for)


async def get_json_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    attempts: int = 3,
    base_delay: float = 0.2,
) -> dict[str, Any] | None:
    """GET url and return JSON; return None for 404.

    Network errors and temporary HTTP errors (429, 5xx) are repeated with
    exponential backoff. Other 4xx errors are raised immediately.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            if status_code == 404:
                return None
            if status_code not in RETRYABLE_STATUS_CODES or attempt == attempts:
                raise
        except httpx.RequestError:
            if attempt == attempts:
                raise
        await asyncio.sleep(base_delay * 2 ** (attempt - 1))

    raise RuntimeError("Unexpected retry state")  # pragma: no cover


async def fetch_product(
    client: httpx.AsyncClient,
    product_id: int,
    *,
    attempts: int = 3,
    base_delay: float = 0.2,
) -> dict[str, Any] | None:
    """Get one product through the REST API (None if it does not exist)."""
    return await get_json_with_retry(
        client,
        f"/products/{product_id}",
        attempts=attempts,
        base_delay=base_delay,
    )


async def fetch_many_products(
    client: httpx.AsyncClient,
    product_ids: list[int],
    *,
    settings: FetchSettings = FetchSettings(),
) -> list[dict[str, Any] | None]:
    """Load several products concurrently.

    * every request is wrapped into an asyncio.Task;
    * asyncio.Semaphore limits how many requests run at the same time;
    * asyncio.gather() waits for all tasks and keeps the order of product_ids.
    """
    semaphore = asyncio.Semaphore(settings.concurrency)

    async def limited_fetch(product_id: int) -> dict[str, Any] | None:
        async with semaphore:
            return await fetch_product(
                client,
                product_id,
                attempts=settings.attempts,
                base_delay=settings.base_delay,
            )

    tasks = [asyncio.create_task(limited_fetch(product_id)) for product_id in product_ids]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        # gather() does not cancel the other tasks when one of them fails
        # (and wait_for() may cancel us): clean everything up.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
