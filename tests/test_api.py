"""Tests for FastAPI endpoints, request validations, and error handling."""

import pytest


def test_health_endpoint(client):
    """GET /api/health returns system and database status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["loaded_count"] == 48
    assert data["rejected_count"] == 3


def test_data_quality_endpoint(client):
    """GET /api/data-quality returns quarantine audit records."""
    res = client.get("/api/data-quality")
    assert res.status_code == 200
    data = res.json()
    assert data["total_records"] == 51
    assert data["loaded_count"] == 48
    assert data["rejected_count"] == 3
    assert len(data["rejected_records"]) == 3


@pytest.mark.parametrize("question,expected_intent", [
    ("What is our total revenue for 2026?", "total_revenue"),
    ("What are the top products by revenue?", "top_product_by_revenue"),
    ("Show me the monthly revenue trend and MoM growth", "monthly_revenue_trend"),
    ("Which region has the highest sales?", "top_region_by_sales"),
    ("Compare revenue between March and April 2026", "compare_months"),
])
def test_ask_five_example_questions(client, question, expected_intent):
    """Verify all 5 required business user questions return valid responses."""
    res = client.post("/api/ask", json={"question": question})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == expected_intent
    assert data["mode"] in ["llm", "fallback"]
    assert len(data["answer"]) > 0
    assert len(data["sql"]) > 0
    assert "3 records excluded" in data["data_notes"]


def test_ask_empty_question_rejected(client):
    """POST /api/ask with empty question returns 400/422 error."""
    res = client.post("/api/ask", json={"question": ""})
    assert res.status_code in [400, 422]


def test_ask_overlong_question_rejected(client):
    """POST /api/ask with question exceeding 500 characters returns 400."""
    long_question = "What is the revenue " * 35  # > 500 chars
    res = client.post("/api/ask", json={"question": long_question})
    assert res.status_code in [400, 422]


def test_ask_unsupported_question(client):
    """POST /api/ask with off-topic question returns 200 with unsupported intent."""
    res = client.post("/api/ask", json={"question": "What is the weather in Tokyo?"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "unsupported"
    assert "Supported question types are" in data["answer"]


def test_ask_gibberish_question(client):
    """POST /api/ask with gibberish returns 200 with unsupported guidance."""
    res = client.post("/api/ask", json={"question": "asdkjasdhqwueyi12983719283"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "unsupported"
