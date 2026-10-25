"""Tests for analytical query templates and math logic."""

import pytest
from app.db import get_read_only_conn
from app.queries import (
    run_total_revenue,
    run_top_product_by_revenue,
    run_monthly_revenue_trend,
    run_top_region_by_sales,
    run_compare_months,
)


def test_top_product_by_revenue(test_data_paths):
    """Verify top 5 products ranking by revenue."""
    conn = get_read_only_conn(test_data_paths["db_path"])
    metrics, supporting, sql = run_top_product_by_revenue(conn, {})
    conn.close()

    assert len(supporting) == 5
    assert supporting[0]["rank"] == 1
    # Check descending order
    for i in range(len(supporting) - 1):
        assert supporting[i]["total_revenue"] >= supporting[i + 1]["total_revenue"]
    assert "top_product" in metrics


def test_monthly_revenue_trend_and_mom(test_data_paths):
    """Verify monthly trend covers 6 months and correctly computes MoM % change."""
    conn = get_read_only_conn(test_data_paths["db_path"])
    metrics, supporting, sql = run_monthly_revenue_trend(conn, {})
    conn.close()

    assert len(supporting) == 6
    months = [r["year_month"] for r in supporting]
    assert months == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

    # First month is baseline
    assert supporting[0]["mom_growth_label"] == "Baseline"

    # Subsequent months have mathematical MoM %
    for i in range(1, 6):
        prev = supporting[i - 1]["total_revenue"]
        curr = supporting[i]["total_revenue"]
        expected_mom = round(((curr - prev) / prev) * 100, 2)
        assert supporting[i]["mom_growth_pct"] == expected_mom


def test_top_region_by_sales(test_data_paths):
    """Verify regions are ranked and revenue share totals ~100%."""
    conn = get_read_only_conn(test_data_paths["db_path"])
    metrics, supporting, sql = run_top_region_by_sales(conn, {})
    conn.close()

    assert len(supporting) == 4
    total_share = sum(r["revenue_share_pct"] for r in supporting)
    assert abs(total_share - 100.0) < 0.5


def test_compare_months_march_vs_april(test_data_paths):
    """Verify comparison between March 2026 and April 2026."""
    conn = get_read_only_conn(test_data_paths["db_path"])
    metrics, supporting, sql = run_compare_months(conn, {"month_a": "2026-03", "month_b": "2026-04"})
    conn.close()

    assert metrics["month_a"] == "2026-03"
    assert metrics["month_b"] == "2026-04"
    assert metrics["revenue_a"] > 0
    assert metrics["revenue_b"] > 0
    expected_diff = round(metrics["revenue_b"] - metrics["revenue_a"], 2)
    assert metrics["absolute_change"] == expected_diff


def test_compare_month_to_itself(test_data_paths):
    """Verify graceful handling when comparing a month to itself."""
    conn = get_read_only_conn(test_data_paths["db_path"])
    metrics, supporting, sql = run_compare_months(conn, {"month_a": "2026-03", "month_b": "2026-03"})
    conn.close()

    assert metrics["absolute_change"] == 0.0
    assert metrics["pct_change"] == 0.0


def test_compare_month_no_data_rejected(test_data_paths):
    """Verify clear error message when requesting a month outside valid range."""
    conn = get_read_only_conn(test_data_paths["db_path"])
    with pytest.raises(ValueError) as exc:
        run_compare_months(conn, {"month_a": "2026-03", "month_b": "2026-11"})
    conn.close()

    assert "No data available" in str(exc.value)
    assert "2026-11" in str(exc.value)
