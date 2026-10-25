# Online Shop — asynchronous REST API

Лабораторна робота №8 «Мережеве та асинхронне програмування. REST API», курс «Професійний Python», варіант №3 — «Інтернет-магазин».
Проєкт продовжує Lab_07 (SQLite, SQLAlchemy, Alembic): REST API працює з тими самими моделями, сервісами та репозиторіями.

## Архітектура

```
HTTP client → FastAPI REST API → Pydantic → Service Layer → Repository Layer → SQLite
```

Асинхронна частина (`POST /products/batch`): `Task` → `asyncio.gather()` → `Semaphore` → `httpx.AsyncClient` (timeout + retry).

## Endpoints

| Method | URL | Опис | Коди |
|---|---|---|---|
| GET | `/` | стан сервісу | 200 |
| GET | `/categories` | список категорій | 200 |
| POST | `/categories` | створити категорію | 201, 409, 422 |
| GET | `/categories/{id}/products` | товари категорії | 200, 404 |
| GET | `/products` | пошук, фільтри, сортування, пагінація | 200, 422 |
| GET | `/products/most-expensive` | найдорожчий товар | 200, 404 |
| GET | `/products/{id}` | товар за id | 200, 404 |
| POST | `/products` | додати товар | 201, 404, 422 |
| PATCH | `/products/{id}` | змінити ціну, кількість, опис, категорію | 200, 404, 422 |
| DELETE | `/products/{id}` | видалити товар | 204, 404 |
| POST | `/products/{id}/purchase` | покупка (транзакція Lab_07) | 201, 404, 409, 422 |
| GET | `/stock/value` | загальна вартість залишків | 200 |
| POST | `/products/batch` | паралельне отримання кількох товарів | 200, 422, 502, 504 |

Query parameters `GET /products`: `category_id`, `q`, `min_price`, `max_price`, `sort_by`, `descending`, `page`, `page_size`.

## Встановлення

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[test]"
```

## Запуск API

```bash
alembic upgrade head            # створити shop.db
python -m uvicorn shop.api:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs, ReDoc: http://127.0.0.1:8000/redoc

Демонстрація роботи з БД з Lab_07: `python -m shop.main`.

## Тести

```bash
python -m pytest -v
```

Тести використовують окрему тимчасову SQLite-базу, `TestClient`, `httpx.ASGITransport` та `httpx.MockTransport` (мок зовнішнього сервісу).

## Структура

```
LAB_08/
├── pyproject.toml, README.md, alembic.ini
├── migrations/, sql/
├── src/shop/
│   ├── api.py            # FastAPI application, endpoints, error handlers
│   ├── schemas.py        # Pydantic schemas
│   ├── dependencies.py   # get_session
│   ├── external_api.py   # HTTPX, Task, gather, Semaphore, timeout, retry
│   ├── database.py, models.py, repositories.py, services.py, dbapi.py   # Lab_07
│   └── exceptions.py, main.py
└── tests/
    ├── conftest.py
    ├── test_api.py, test_external_api.py
    └── test_repositories.py, test_services.py, test_constraints.py, test_dbapi.py, test_migrations.py   # Lab_07
```
