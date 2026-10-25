"""Entry points of the online shop: database demo (Lab 7) and API server (Lab 8)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from shop.database import SessionLocal, engine
from shop.dbapi import find_products_by_category, search_products
from shop.exceptions import InsufficientStockError
from shop.models import Base, Product
from shop.repositories import (
    CategoryRepository,
    ProductRepository,
    PurchaseRepository,
)
from shop.services import ShopService, purchase_product


def print_products(title: str, products: list[Product]) -> None:
    print(f"\n{title}")
    print(f"{'ID':>3}  {'Product':<22}{'Price':>10}{'Qty':>6}")
    print("-" * 43)
    for item in products:
        print(f"{item.id:>3}  {item.name:<22}{item.price:>10.2f}{item.quantity:>6}")


def seed(session: Session) -> None:
    """Fill an empty database with demo data."""
    categories = CategoryRepository(session)
    products = ProductRepository(session)
    if products.count() > 0:
        return

    electronics = categories.get_by_name("Electronics") or categories.add("Electronics")
    books = categories.get_by_name("Books") or categories.add("Books")

    demo_products = [
        Product(name="Laptop", price=1200.0, quantity=5, category_id=electronics.id,
                description="15-inch laptop"),
        Product(name="Mouse", price=25.5, quantity=40, category_id=electronics.id),
        Product(name="Keyboard", price=60.0, quantity=15, category_id=electronics.id),
        Product(name="Python Basics", price=32.0, quantity=12, category_id=books.id),
        Product(name="SQL Handbook", price=45.0, quantity=8, category_id=books.id),
    ]
    for product in demo_products:
        products.add(product)


def main() -> None:
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        categories = CategoryRepository(session)
        products = ProductRepository(session)
        purchases = PurchaseRepository(session)
        service = ShopService(session)

        seed(session)

        print_products("ALL PRODUCTS", products.get_all())

        electronics = categories.get_by_name("Electronics")
        if electronics is not None:
            print_products(
                "PRODUCTS OF CATEGORY 'Electronics'",
                products.filter_by_category(electronics.id),
            )

        print(f"\nStock value: {service.get_stock_value():.2f}")
        print(f"Average price: {service.get_average_price():.2f}")
        most_expensive = service.get_most_expensive_product()
        if most_expensive is not None:
            print(f"Most expensive: {most_expensive.name} ({most_expensive.price:.2f})")

        print("\nSTATISTICS BY CATEGORY (JOIN + GROUP BY)")
        for stats in service.get_category_stats():
            print(f"{stats.name:<12} products={stats.product_count:<3} "
                  f"value={stats.stock_value:.2f}")

        # DB-API (sqlite3) with parameterized queries
        database_path = engine.url.database
        if database_path is not None:
            print("\nDB-API: products of 'Books'")
            for name, price, quantity in find_products_by_category(database_path, "Books"):
                print(f"  {name:<20}{price:>8.2f}{quantity:>5}")
            print("DB-API: search 'o' with max price 50")
            for name, category, price, quantity in search_products(
                database_path, name_part="o", max_price=50.0
            ):
                print(f"  {name:<20}{category:<12}{price:>8.2f}{quantity:>5}")

        # Transaction: successful purchase and a rolled back one
        found = products.find_by_name("Laptop")
        if found:
            laptop = found[0]
            purchase = purchase_product(session, laptop.id, 1)
            print(f"\nPurchase #{purchase.id}: {purchase.quantity} x {laptop.name} "
                  f"= {purchase.total_price:.2f}")
            try:
                purchase_product(session, laptop.id, 10_000)
            except InsufficientStockError as error:
                print(f"Rollback: {error}")
            session.refresh(laptop)
            print(f"Laptop quantity after the failed purchase: {laptop.quantity}")
            print(f"Purchases in history: {purchases.count()}")


def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Run the REST API with Uvicorn (Swagger UI: http://127.0.0.1:8000/docs)."""
    import uvicorn

    uvicorn.run("shop.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
