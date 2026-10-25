-- Final schema of the online shop (SQLite).
-- It is equivalent to what SQLAlchemy emits for Base.metadata.create_all().
-- Column "description" in products is added by the Alembic migration 0002.

CREATE TABLE categories (
    id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (name)
);

CREATE TABLE products (
    id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    price FLOAT NOT NULL,
    quantity INTEGER NOT NULL,
    description TEXT,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_products_price_non_negative CHECK (price >= 0),
    CONSTRAINT ck_products_quantity_non_negative CHECK (quantity >= 0),
    FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
);

CREATE TABLE purchases (
    id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    total_price FLOAT NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_purchases_quantity_positive CHECK (quantity > 0),
    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
);
