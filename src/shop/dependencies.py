"""FastAPI dependencies (dependency injection)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.orm import Session

from shop.database import SessionLocal


async def get_session() -> AsyncGenerator[Session, None]:
    """Provide a database session for one request and always close it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
