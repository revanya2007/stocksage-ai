import sqlite3
from pathlib import Path

# Get root directory of repository dynamically
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "stocksage.db"

def get_db_path() -> Path:
    """Return absolute path to SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH

def get_connection(db_path=None) -> sqlite3.Connection:
    """Return a SQLite connection with foreign keys enabled and Row factory."""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def initialize_database():
    """Create tables and indexes if they do not exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Stores table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stores (
        store_id INTEGER PRIMARY KEY,
        store_name TEXT NOT NULL,
        location TEXT NOT NULL
    );
    """)

    # Products table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY,
        product_name TEXT NOT NULL,
        category TEXT NOT NULL,
        selling_price REAL NOT NULL CHECK(selling_price > 0)
    );
    """)

    # Sales table (transaction line items)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        sale_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT NOT NULL,
        date TEXT NOT NULL,
        store_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity_sold INTEGER NOT NULL CHECK(quantity_sold >= 0),
        sales_amount REAL NOT NULL CHECK(sales_amount >= 0),
        FOREIGN KEY (store_id) REFERENCES stores(store_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );
    """)

    # Inventory table (composite PK)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        store_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        current_stock INTEGER NOT NULL CHECK(current_stock >= 0),
        reorder_level INTEGER NOT NULL CHECK(reorder_level >= 0),
        last_updated TEXT NOT NULL,
        PRIMARY KEY (store_id, product_id),
        FOREIGN KEY (store_id) REFERENCES stores(store_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );
    """)

    # Recommendations table (prepared for later phases)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recommendations (
        recommendation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        store_id INTEGER,
        product_id INTEGER NOT NULL,
        issue_type TEXT NOT NULL,
        priority_score REAL,
        evidence TEXT,
        recommendation TEXT,
        confidence TEXT,
        manager_action TEXT DEFAULT 'Review',
        FOREIGN KEY (product_id) REFERENCES products(product_id),
        FOREIGN KEY (store_id) REFERENCES stores(store_id)
    );
    """)

    # Backward-compatible check to add store_id if missing in existing database
    cursor.execute("PRAGMA table_info(recommendations);")
    columns = [col[1] for col in cursor.fetchall()]
    if "store_id" not in columns:
        cursor.execute("ALTER TABLE recommendations ADD COLUMN store_id INTEGER;")

    # Performance Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(product_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_store ON sales(store_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_store_product ON sales(store_id, product_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_txn ON sales(transaction_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_product ON inventory(product_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_store ON inventory(store_id);")

    conn.commit()
    conn.close()

def reset_database():
    """Drop existing tables safely and re-initialize database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    tables = ["recommendations", "inventory", "sales", "products", "stores"]
    for table in tables:
        cursor.execute(f"DROP TABLE IF EXISTS {table};")

    conn.commit()
    conn.close()
    initialize_database()

def get_table_counts() -> dict:
    """Return dictionary of row counts for each database table."""
    conn = get_connection()
    cursor = conn.cursor()

    counts = {}
    tables = ["stores", "products", "sales", "inventory", "recommendations"]
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            counts[table] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            counts[table] = 0

    conn.close()
    return counts

def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists
