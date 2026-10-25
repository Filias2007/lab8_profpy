"""Integration tests: Alembic migrations on a temporary SQLite database."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from shop.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(db_path: Path) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return config


def _product_columns(db_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns("products")}
    finally:
        engine.dispose()


def test_migration_adds_description_column(tmp_path: Path) -> None:
    db_path = tmp_path / "migrated.db"
    config = _alembic_config(db_path)

    command.upgrade(config, "0001")
    assert "description" not in _product_columns(db_path)

    command.upgrade(config, "head")
    assert "description" in _product_columns(db_path)


def test_migration_downgrade_removes_description_column(tmp_path: Path) -> None:
    db_path = tmp_path / "migrated.db"
    config = _alembic_config(db_path)
    command.upgrade(config, "head")

    command.downgrade(config, "0001")

    assert "description" not in _product_columns(db_path)


def test_migration_on_database_created_by_orm(tmp_path: Path) -> None:
    """upgrade head must not fail when create_all() has already made the tables."""
    db_path = tmp_path / "orm_created.db"
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    command.upgrade(_alembic_config(db_path), "head")

    assert "description" in _product_columns(db_path)
