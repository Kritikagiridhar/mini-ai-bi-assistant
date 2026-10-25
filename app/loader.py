"""Data ingestion, validation, and quarantine pipeline."""

import json
import logging
from pathlib import Path
from typing import Any
import pandas as pd

from app.db import get_write_conn, init_db
from app.intents import (
    BUSINESS_REVENUE_DEFINITION,
    VALID_STATUSES,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def validate_and_clean_row(
    row: dict[str, Any], seen_ids: set[str]
) -> tuple[bool, str, dict[str, Any]]:
    """Generic row-level validation rule engine.
    
    Returns:
        (is_valid, rejection_reason, cleaned_data_dict)
    """
    txn_id = str(row.get("Transaction_Id", "")).strip()
    if not txn_id or txn_id.lower() == "nan":
        return False, "Missing Transaction_Id", {}

    if txn_id in seen_ids:
        return False, f"Duplicate Transaction_Id: {txn_id}", {}
    seen_ids.add(txn_id)

    # 1. Date Validation (DD-MM-YYYY -> ISO YYYY-MM-DD + YYYY-MM)
    raw_date = str(row.get("Order_date", "")).strip()
    try:
        parsed_date = pd.to_datetime(raw_date, dayfirst=True, format="%d-%m-%Y", errors="coerce")
        if pd.isna(parsed_date):
            return False, f"Invalid date format '{raw_date}': must be DD-MM-YYYY", {}
        iso_date = parsed_date.strftime("%Y-%m-%d")
        year_month = parsed_date.strftime("%Y-%m")
    except Exception as exc:
        return False, f"Unparseable date '{raw_date}': {exc}", {}

    # 2. Quantity Validation (must be positive integer)
    raw_qty = row.get("Quantity")
    try:
        if pd.isna(raw_qty) or str(raw_qty).strip() == "":
            return False, "Missing Quantity value", {}
        qty = int(raw_qty)
        if qty <= 0:
            return False, f"Invalid quantity: {qty} (must be a positive integer > 0)", {}
    except (ValueError, TypeError):
        return False, f"Non-numeric quantity: '{raw_qty}'", {}

    # 3. Unit Price Validation (must be present and > 0, never guess)
    raw_price = row.get("Unit_price")
    try:
        if pd.isna(raw_price) or str(raw_price).strip() == "":
            return False, "Missing Unit_price (quarantined without guessing)", {}
        unit_price = float(raw_price)
        if unit_price <= 0.0:
            return False, f"Invalid unit price: {unit_price} (must be > 0.0)", {}
    except (ValueError, TypeError):
        return False, f"Non-numeric unit price: '{raw_price}'", {}

    # 4. Discount Amount Validation
    raw_discount = row.get("Discount_amount", 0.0)
    try:
        discount = float(raw_discount) if not pd.isna(raw_discount) and str(raw_discount).strip() != "" else 0.0
        if discount < 0.0:
            return False, f"Negative discount amount: {discount}", {}
        gross_value = qty * unit_price
        if discount > gross_value:
            return False, f"Discount {discount} exceeds line total {gross_value}", {}
    except (ValueError, TypeError):
        return False, f"Non-numeric discount amount: '{raw_discount}'", {}

    # 5. Status Validation (Exclude returned or invalid status from revenue)
    status = str(row.get("Status", "")).strip()
    if not status or status.lower() == "nan":
        return False, "Missing order Status", {}
    if status not in VALID_STATUSES:
        return False, f"Unknown order status: '{status}'", {}
    if status != "Completed":
        return False, f"Status is '{status}' (only Completed orders are included in revenue)", {}

    # 6. String Fields
    product = str(row.get("Product", "")).strip()
    category = str(row.get("Category", "")).strip()
    region = str(row.get("Region", "")).strip().capitalize()
    sales_channel = str(row.get("Sales_channel", "")).strip().capitalize()

    if not product or not category or not region or not sales_channel:
        return False, "Missing required dimension attribute (Product/Category/Region/Channel)", {}

    # 7. Revenue calculation (per business definition)
    # Revenue = Quantity * Unit_price - Discount_amount
    revenue = round((qty * unit_price) - discount, 2)

    cleaned = {
        "transaction_id": txn_id,
        "order_date": iso_date,
        "year_month": year_month,
        "product": product,
        "category": category,
        "region": region,
        "sales_channel": sales_channel,
        "quantity": qty,
        "unit_price": round(unit_price, 2),
        "discount_amount": round(discount, 2),
        "status": status,
        "revenue": revenue,
    }
    return True, "", cleaned


def load_csv_to_db(csv_path: Path | str, db_path: Path | str) -> dict[str, Any]:
    """Ingest CSV, apply generic data quality validation, and populate SQLite tables.
    
    Valid rows are stored in `sales`.
    Invalid/quarantined rows are stored in `rejected_records`.
    """
    csv_file = Path(csv_path).resolve()
    if not csv_file.exists():
        raise FileNotFoundError(f"Source sales CSV file does not exist at {csv_file}")

    # Ensure tables exist
    init_db(db_path)

    # Read raw CSV with string types to preserve original inputs
    df = pd.read_csv(csv_file, dtype=str)
    raw_records = df.to_dict(orient="records")

    conn = get_write_conn(db_path)
    cursor = conn.cursor()

    # Clear prior load to support idempotent re-runs
    cursor.execute("DELETE FROM sales")
    cursor.execute("DELETE FROM rejected_records")

    loaded_rows = []
    rejected_rows = []
    reason_counts: dict[str, int] = {}
    seen_ids: set[str] = set()

    for row in raw_records:
        txn_id = str(row.get("Transaction_Id", "")).strip()
        is_valid, reason, cleaned_data = validate_and_clean_row(row, seen_ids)

        if is_valid:
            loaded_rows.append(cleaned_data)
        else:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            rejected_rows.append({
                "transaction_id": txn_id if txn_id else None,
                "row_data": json.dumps(row),
                "reason": reason,
            })

    # Batch insert into sales
    if loaded_rows:
        cursor.executemany("""
            INSERT INTO sales (
                transaction_id, order_date, year_month, product, category,
                region, sales_channel, quantity, unit_price, discount_amount,
                status, revenue
            ) VALUES (
                :transaction_id, :order_date, :year_month, :product, :category,
                :region, :sales_channel, :quantity, :unit_price, :discount_amount,
                :status, :revenue
            )
        """, loaded_rows)

    # Batch insert into rejected_records
    if rejected_rows:
        cursor.executemany("""
            INSERT INTO rejected_records (transaction_id, row_data, reason)
            VALUES (:transaction_id, :row_data, :reason)
        """, rejected_rows)

    conn.commit()
    conn.close()

    summary = {
        "total_source_rows": len(raw_records),
        "loaded_count": len(loaded_rows),
        "rejected_count": len(rejected_rows),
        "rejection_breakdown": reason_counts,
        "business_definition": BUSINESS_REVENUE_DEFINITION,
    }

    logger.info(
        "Data Ingestion Complete: Loaded %d, Rejected %d (Reasons: %s)",
        summary["loaded_count"],
        summary["rejected_count"],
        summary["rejection_breakdown"],
    )

    return summary
