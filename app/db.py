"""Database setup and connection helpers for SQLite."""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sales.db"


def get_write_conn(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Return a read-write SQLite connection used strictly during setup and ingestion."""
    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def get_read_only_conn(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Return a strictly read-only SQLite connection for query execution."""
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Database file not found at {path}. Initialize it first.")

    # SQLite URI with mode=ro enforces filesystem-level read-only access
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Create sales and rejected_records tables along with query indexes."""
    conn = get_write_conn(db_path)
    try:
        cursor = conn.cursor()

        # Clean/valid sales transactions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                transaction_id TEXT PRIMARY KEY,
                order_date TEXT NOT NULL,
                year_month TEXT NOT NULL,
                product TEXT NOT NULL,
                category TEXT NOT NULL,
                region TEXT NOT NULL,
                sales_channel TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                discount_amount REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL,
                revenue REAL NOT NULL
            )
        """)

        # Quarantined / rejected records with rejection audit trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rejected_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT,
                row_data TEXT NOT NULL,
                reason TEXT NOT NULL,
                rejected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Performance indexes for analytics queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_ym ON sales(year_month)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_prod ON sales(product)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_cat ON sales(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_reg ON sales(region)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_chan ON sales(sales_channel)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_stat ON sales(status)")

        conn.commit()
    finally:
        conn.close()
