"""Pytest fixtures for temporary databases, clients, and mocks."""

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.db import init_db
from app.loader import load_csv_to_db
import app.main as main_module


@pytest.fixture(scope="session")
def test_data_paths(tmp_path_factory):
    """Create isolated test database and return paths."""
    temp_dir = tmp_path_factory.mktemp("test_db_dir")
    db_path = temp_dir / "test_sales.db"
    csv_path = Path(__file__).resolve().parent.parent / "data" / "ai_bi_assistant_sales_data.csv"

    # Initialize and load data
    load_csv_to_db(csv_path, db_path)
    return {"csv_path": csv_path, "db_path": db_path}


@pytest.fixture
def client(test_data_paths, monkeypatch):
    """FastAPI TestClient with isolated test database."""
    test_db = test_data_paths["db_path"]
    monkeypatch.setattr(main_module, "DB_PATH", test_db)

    # Disable real LLM to guarantee deterministic testing across the suite
    from app.llm_client import GeminiLLMClient
    mock_client = GeminiLLMClient(api_key=None)
    main_module.app_state["llm_client"] = mock_client

    with TestClient(main_module.app) as test_client:
        yield test_client
