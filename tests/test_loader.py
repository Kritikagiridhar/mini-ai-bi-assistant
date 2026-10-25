"""Tests for data loading, generic validation, quarantine, and pandas reconciliation."""

import sqlite3
import pandas as pd
from app.db import get_read_only_conn
from app.loader import load_csv_to_db


def test_quarantined_records_and_counts(test_data_paths):
    """Verify that exactly 3 known problematic records are quarantined with reasons."""
    db_path = test_data_paths["db_path"]
    conn = get_read_only_conn(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as count FROM sales")
    valid_count = cur.fetchone()["count"]
    assert valid_count == 48, f"Expected 48 valid rows, got {valid_count}"

    cur.execute("SELECT transaction_id, reason FROM rejected_records")
    rejected_rows = cur.fetchall()
    conn.close()

    assert len(rejected_rows) == 3, f"Expected 3 rejected rows, got {len(rejected_rows)}"
    rejected_map = {r["transaction_id"]: r["reason"] for r in rejected_rows}

    # TXN0033: Returned
    assert "TXN0033" in rejected_map
    assert "Returned" in rejected_map["TXN0033"]

    # TXN0034: Quantity = 0
    assert "TXN0034" in rejected_map
    assert "quantity" in rejected_map["TXN0034"].lower()

    # TXN0051: Missing Unit_price
    assert "TXN0051" in rejected_map
    assert "price" in rejected_map["TXN0051"].lower()


def test_total_revenue_equals_independent_pandas_benchmark(test_data_paths):
    """Assert that total revenue in SQLite strictly matches independent pandas calculation."""
    csv_path = test_data_paths["csv_path"]
    db_path = test_data_paths["db_path"]

    # 1. Independent pandas computation
    raw_df = pd.read_csv(csv_path)

    # Clean according to business rules
    clean_df = raw_df[
        (raw_df["Status"] == "Completed")
        & (pd.to_numeric(raw_df["Quantity"], errors="coerce") > 0)
        & (pd.to_numeric(raw_df["Unit_price"], errors="coerce") > 0)
        & (pd.to_numeric(raw_df["Unit_price"], errors="coerce").notna())
    ].copy()

    clean_df["Quantity"] = clean_df["Quantity"].astype(float)
    clean_df["Unit_price"] = clean_df["Unit_price"].astype(float)
    clean_df["Discount_amount"] = clean_df["Discount_amount"].fillna(0.0).astype(float)

    clean_df["line_revenue"] = (clean_df["Quantity"] * clean_df["Unit_price"]) - clean_df["Discount_amount"]
    expected_revenue = round(clean_df["line_revenue"].sum(), 2)

    # 2. SQLite query
    conn = get_read_only_conn(db_path)
    cur = conn.cursor()
    cur.execute("SELECT ROUND(SUM(revenue), 2) as total_rev FROM sales WHERE status = 'Completed'")
    actual_revenue = round(cur.fetchone()["total_rev"], 2)
    conn.close()

    assert actual_revenue == expected_revenue, (
        f"Database revenue ${actual_revenue} does not match pandas benchmark ${expected_revenue}"
    )
