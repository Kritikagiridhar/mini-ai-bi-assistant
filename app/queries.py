"""Parameterized SQL query templates and analytical calculations.

All queries are executed against a read-only SQLite connection and inspected
by sql_guard as a defense-in-depth measure.
"""

import sqlite3
from typing import Any
from app.intents import (
    INTENT_TOTAL_REVENUE,
    INTENT_TOP_PRODUCT_BY_REVENUE,
    INTENT_MONTHLY_REVENUE_TREND,
    INTENT_TOP_REGION_BY_SALES,
    INTENT_COMPARE_MONTHS,
    VALID_MONTHS,
)
from app.sql_guard import validate_safe_query


def run_total_revenue(
    conn: sqlite3.Connection, params: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Execute total_revenue query with optional dimension filters."""
    where_clauses = ["status = 'Completed'"]
    sql_params: dict[str, Any] = {}

    if params.get("product"):
        where_clauses.append("LOWER(product) = LOWER(:product)")
        sql_params["product"] = str(params["product"]).strip()

    if params.get("category"):
        where_clauses.append("LOWER(category) = LOWER(:category)")
        sql_params["category"] = str(params["category"]).strip()

    if params.get("region"):
        where_clauses.append("LOWER(region) = LOWER(:region)")
        sql_params["region"] = str(params["region"]).strip()

    channel = params.get("sales_channel") or params.get("channel")
    if channel:
        where_clauses.append("LOWER(sales_channel) = LOWER(:channel)")
        sql_params["channel"] = str(channel).strip()

    month = params.get("year_month") or params.get("month")
    if month:
        where_clauses.append("year_month = :year_month")
        sql_params["year_month"] = str(month).strip()

    sql = f"""
SELECT 
    ROUND(COALESCE(SUM(revenue), 0.0), 2) AS total_revenue,
    COUNT(*) AS transaction_count,
    COALESCE(SUM(quantity), 0) AS total_quantity,
    ROUND(COALESCE(AVG(revenue), 0.0), 2) AS average_order_value
FROM sales
WHERE {" AND ".join(where_clauses)}
""".strip()

    validate_safe_query(sql)
    cursor = conn.cursor()
    cursor.execute(sql, sql_params)
    row = cursor.fetchone()

    total_revenue = float(row["total_revenue"]) if row and row["total_revenue"] is not None else 0.0
    txn_count = int(row["transaction_count"]) if row and row["transaction_count"] is not None else 0
    total_qty = int(row["total_quantity"]) if row and row["total_quantity"] is not None else 0
    aov = float(row["average_order_value"]) if row and row["average_order_value"] is not None else 0.0

    supporting_data = [{
        "total_revenue": total_revenue,
        "transaction_count": txn_count,
        "total_quantity": total_qty,
        "average_order_value": aov,
    }]

    filter_desc = []
    if "product" in sql_params:
        filter_desc.append(f"product '{sql_params['product']}'")
    if "category" in sql_params:
        filter_desc.append(f"category '{sql_params['category']}'")
    if "region" in sql_params:
        filter_desc.append(f"region '{sql_params['region']}'")
    if "channel" in sql_params:
        filter_desc.append(f"channel '{sql_params['channel']}'")
    if "year_month" in sql_params:
        filter_desc.append(f"month '{sql_params['year_month']}'")

    qualifier = f" for {', '.join(filter_desc)}" if filter_desc else ""
    answer = (
        f"Total revenue{qualifier} is ${total_revenue:,.2f} across "
        f"{txn_count} completed transactions ({total_qty} units sold, avg order value ${aov:,.2f})."
    )

    return {
        "total_revenue": total_revenue,
        "transaction_count": txn_count,
        "total_quantity": total_qty,
        "average_order_value": aov,
        "answer": answer,
    }, supporting_data, sql


def run_top_product_by_revenue(
    conn: sqlite3.Connection, params: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Execute top_product_by_revenue returning top 5 ranked products."""
    where_clauses = ["status = 'Completed'"]
    sql_params: dict[str, Any] = {}

    if params.get("region"):
        where_clauses.append("LOWER(region) = LOWER(:region)")
        sql_params["region"] = str(params["region"]).strip()

    month = params.get("year_month") or params.get("month")
    if month:
        where_clauses.append("year_month = :year_month")
        sql_params["year_month"] = str(month).strip()

    sql = f"""
SELECT 
    product,
    category,
    SUM(quantity) AS units_sold,
    ROUND(SUM(revenue), 2) AS total_revenue
FROM sales
WHERE {" AND ".join(where_clauses)}
GROUP BY product
ORDER BY total_revenue DESC
LIMIT 5
""".strip()

    validate_safe_query(sql)
    cursor = conn.cursor()
    cursor.execute(sql, sql_params)
    rows = cursor.fetchall()

    supporting_data = []
    for rank, row in enumerate(rows, 1):
        supporting_data.append({
            "rank": rank,
            "product": row["product"],
            "category": row["category"],
            "units_sold": int(row["units_sold"]),
            "total_revenue": float(row["total_revenue"]),
        })

    if not supporting_data:
        return {}, [], sql

    top_item = supporting_data[0]
    filter_desc = []
    if "region" in sql_params:
        filter_desc.append(f"in the {sql_params['region']} region")
    if "year_month" in sql_params:
        filter_desc.append(f"in {sql_params['year_month']}")
    qualifier = f" ({', '.join(filter_desc)})" if filter_desc else ""

    answer = (
        f"The top product by revenue{qualifier} is '{top_item['product']}' "
        f"with ${top_item['total_revenue']:,.2f} in sales ({top_item['units_sold']} units sold). "
        f"The top 5 ranked products are listed in the table below."
    )
    return {
        "top_product": top_item["product"],
        "top_revenue": top_item["total_revenue"],
        "units_sold": top_item["units_sold"],
        "answer": answer,
    }, supporting_data, sql


def run_monthly_revenue_trend(
    conn: sqlite3.Connection, params: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Execute monthly_revenue_trend across all 6 months with MoM growth %."""
    sql = """
SELECT 
    year_month,
    ROUND(SUM(revenue), 2) AS total_revenue,
    COUNT(*) AS transaction_count,
    SUM(quantity) AS total_quantity
FROM sales
WHERE status = 'Completed'
GROUP BY year_month
ORDER BY year_month ASC
""".strip()

    validate_safe_query(sql)
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()

    supporting_data = []
    prev_revenue = None
    peak_month = ""
    peak_revenue = -1.0

    for idx, row in enumerate(rows):
        current_rev = float(row["total_revenue"])
        if current_rev > peak_revenue:
            peak_revenue = current_rev
            peak_month = row["year_month"]

        if prev_revenue is None or prev_revenue == 0:
            mom_growth_pct = 0.0
            mom_label = "Baseline"
        else:
            mom_growth_pct = round(((current_rev - prev_revenue) / prev_revenue) * 100, 2)
            mom_label = f"{mom_growth_pct:+.2f}%"

        supporting_data.append({
            "year_month": row["year_month"],
            "total_revenue": current_rev,
            "transaction_count": int(row["transaction_count"]),
            "total_quantity": int(row["total_quantity"]),
            "mom_growth_pct": mom_growth_pct,
            "mom_growth_label": mom_label,
        })
        prev_revenue = current_rev

    answer = (
        f"Sales data spans {len(supporting_data)} months (Jan 2026 to Jun 2026). "
        f"Peak monthly revenue was reached in {peak_month} at ${peak_revenue:,.2f}. "
        f"Full Month-over-Month (MoM) trajectory is visualized below."
    )

    return {
        "peak_month": peak_month,
        "peak_revenue": peak_revenue,
        "answer": answer,
    }, supporting_data, sql


def run_top_region_by_sales(
    conn: sqlite3.Connection, params: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Execute top_region_by_sales ranked by total revenue and market share."""
    sql = """
SELECT 
    region,
    ROUND(SUM(revenue), 2) AS total_revenue,
    COUNT(*) AS transaction_count,
    SUM(quantity) AS total_quantity
FROM sales
WHERE status = 'Completed'
GROUP BY region
ORDER BY total_revenue DESC
""".strip()

    validate_safe_query(sql)
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()

    total_all_regions = sum(float(r["total_revenue"]) for r in rows) if rows else 0.0

    supporting_data = []
    for rank, row in enumerate(rows, 1):
        rev = float(row["total_revenue"])
        share = round((rev / total_all_regions * 100), 2) if total_all_regions > 0 else 0.0
        supporting_data.append({
            "rank": rank,
            "region": row["region"],
            "total_revenue": rev,
            "transaction_count": int(row["transaction_count"]),
            "total_quantity": int(row["total_quantity"]),
            "revenue_share_pct": share,
        })

    if not supporting_data:
        return {}, [], sql

    top_region = supporting_data[0]
    answer = (
        f"The top region by sales is '{top_region['region']}' with ${top_region['total_revenue']:,.2f} "
        f"in total revenue ({top_region['revenue_share_pct']}% of total sales across all regions)."
    )

    return {
        "top_region": top_region["region"],
        "top_revenue": top_region["total_revenue"],
        "revenue_share_pct": top_region["revenue_share_pct"],
        "answer": answer,
    }, supporting_data, sql


def run_compare_months(
    conn: sqlite3.Connection, params: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Compare performance metrics between two specific months."""
    month_a = params.get("month_a")
    month_b = params.get("month_b")

    if not month_a or not month_b:
        raise ValueError("Both 'month_a' and 'month_b' must be provided for month comparison.")

    month_a = str(month_a).strip()
    month_b = str(month_b).strip()

    # Reject months with no data with a clear message
    invalid_months = []
    if month_a not in VALID_MONTHS:
        invalid_months.append(month_a)
    if month_b not in VALID_MONTHS:
        invalid_months.append(month_b)

    if invalid_months:
        joined_invalid = ", ".join(invalid_months)
        valid_range = f"{VALID_MONTHS[0]} to {VALID_MONTHS[-1]}"
        raise ValueError(
            f"No data available for requested month(s): {joined_invalid}. Valid data exists only between {valid_range}."
        )

    # Edge case: comparing a month to itself
    if month_a == month_b:
        sql = """
SELECT 
    year_month,
    ROUND(SUM(revenue), 2) AS total_revenue,
    COUNT(*) AS transaction_count,
    SUM(quantity) AS total_quantity
FROM sales
WHERE status = 'Completed' AND year_month = :month_a
GROUP BY year_month
""".strip()
        validate_safe_query(sql)
        cursor = conn.cursor()
        cursor.execute(sql, {"month_a": month_a})
        row = cursor.fetchone()
        rev = float(row["total_revenue"]) if row else 0.0
        supporting_data = [{
            "month": month_a,
            "total_revenue": rev,
            "transaction_count": int(row["transaction_count"]) if row else 0,
            "total_quantity": int(row["total_quantity"]) if row else 0,
            "comparison": "Self-comparison (0.00% change)",
        }]
        answer = f"Comparing {month_a} to itself: revenue is identical at ${rev:,.2f} ($0.00 absolute change, 0.00%)."
        return {"month_a": month_a, "month_b": month_b, "absolute_change": 0.0, "pct_change": 0.0}, supporting_data, sql

    sql = """
SELECT 
    year_month,
    ROUND(SUM(revenue), 2) AS total_revenue,
    COUNT(*) AS transaction_count,
    SUM(quantity) AS total_quantity
FROM sales
WHERE status = 'Completed' AND year_month IN (:month_a, :month_b)
GROUP BY year_month
ORDER BY year_month ASC
""".strip()

    validate_safe_query(sql)
    cursor = conn.cursor()
    cursor.execute(sql, {"month_a": month_a, "month_b": month_b})
    rows = cursor.fetchall()

    month_data = {r["year_month"]: r for r in rows}
    rev_a = float(month_data[month_a]["total_revenue"]) if month_a in month_data else 0.0
    rev_b = float(month_data[month_b]["total_revenue"]) if month_b in month_data else 0.0

    abs_diff = round(rev_b - rev_a, 2)
    pct_diff = round(((rev_b - rev_a) / rev_a) * 100, 2) if rev_a > 0 else 0.0

    supporting_data = [
        {
            "month": month_a,
            "total_revenue": rev_a,
            "transaction_count": int(month_data[month_a]["transaction_count"]) if month_a in month_data else 0,
            "total_quantity": int(month_data[month_a]["total_quantity"]) if month_a in month_data else 0,
        },
        {
            "month": month_b,
            "total_revenue": rev_b,
            "transaction_count": int(month_data[month_b]["transaction_count"]) if month_b in month_data else 0,
            "total_quantity": int(month_data[month_b]["total_quantity"]) if month_b in month_data else 0,
        },
    ]

    trend_verb = "increased" if abs_diff > 0 else ("decreased" if abs_diff < 0 else "remained flat")
    answer = (
        f"Comparing {month_a} (${rev_a:,.2f}) vs {month_b} (${rev_b:,.2f}): "
        f"revenue {trend_verb} by ${abs(abs_diff):,.2f} ({pct_diff:+.2f}%)."
    )

    metrics = {
        "month_a": month_a,
        "revenue_a": rev_a,
        "month_b": month_b,
        "revenue_b": rev_b,
        "absolute_change": abs_diff,
        "pct_change": pct_diff,
        "answer": answer,
    }
    return metrics, supporting_data, sql


QUERY_HANDLERS = {
    INTENT_TOTAL_REVENUE: run_total_revenue,
    INTENT_TOP_PRODUCT_BY_REVENUE: run_top_product_by_revenue,
    INTENT_MONTHLY_REVENUE_TREND: run_monthly_revenue_trend,
    INTENT_TOP_REGION_BY_SALES: run_top_region_by_sales,
    INTENT_COMPARE_MONTHS: run_compare_months,
}
