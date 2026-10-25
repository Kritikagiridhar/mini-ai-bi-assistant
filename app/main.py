"""Main FastAPI application entrypoint.

Provides business intelligence query endpoints, health check, data quality audit,
and static frontend hosting.
"""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import DEFAULT_DB_PATH, get_read_only_conn
from app.intents import (
    INTENT_UNSUPPORTED,
    UNSUPPORTED_GUIDANCE_MESSAGE,
    WHITELISTED_INTENTS,
)
from app.llm_client import GeminiLLMClient
from app.loader import load_csv_to_db
from app.queries import QUERY_HANDLERS
from app.router import route_question, verify_or_replace_summary
from app.schemas import AskRequest, AskResponse, DataQualityResponse, HealthResponse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
CSV_PATH = DATA_DIR / "ai_bi_assistant_sales_data.csv"
DB_PATH = DATA_DIR / "sales.db"

# Global state
app_state: dict[str, Any] = {
    "llm_client": None,
    "load_summary": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing database initialization and LLM setup."""
    logger.info("Initializing Mini AI BI Assistant service...")
    try:
        # Load and validate CSV dataset
        summary = load_csv_to_db(CSV_PATH, DB_PATH)
        app_state["load_summary"] = summary
        logger.info("Database loaded successfully: %s", summary)
    except Exception as exc:
        logger.error("Failed during initial data ingestion: %s", exc)

    # Initialize LLM client
    app_state["llm_client"] = GeminiLLMClient()
    if app_state["llm_client"].is_available():
        logger.info("Gemini LLM client initialized successfully.")
    else:
        logger.info("GEMINI_API_KEY not configured or unavailable. Operating in fallback mode.")

    yield
    logger.info("Shutting down Mini AI BI Assistant service.")


app = FastAPI(
    title="Mini AI Business Intelligence Assistant",
    description="Deterministic AI-powered sales data analytics with guaranteed mathematical correctness.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return clean, user-friendly 400/422 validation errors."""
    errors = exc.errors()
    first_error = errors[0] if errors else {}
    msg = first_error.get("msg", "Invalid request parameters.")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": f"Validation error: {msg}"},
    )


@app.get("/api/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Service health and database status check."""
    loaded = 0
    rejected = 0
    db_status = "disconnected"

    try:
        conn = get_read_only_conn(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM sales")
        loaded = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) AS cnt FROM rejected_records")
        rejected = cur.fetchone()["cnt"]
        conn.close()
        db_status = "connected"
    except Exception as exc:
        db_status = f"error: {exc}"

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        database=db_status,
        loaded_count=loaded,
        rejected_count=rejected,
    )


@app.get("/api/data-quality", response_model=DataQualityResponse)
def data_quality_audit() -> DataQualityResponse:
    """Audit endpoint listing quarantined records and rejection reasons."""
    try:
        conn = get_read_only_conn(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM sales")
        loaded = cur.fetchone()["cnt"]

        cur.execute("SELECT transaction_id, row_data, reason, rejected_at FROM rejected_records")
        rejected_rows = [dict(r) for r in cur.fetchall()]
        conn.close()

        total = loaded + len(rejected_rows)
        return DataQualityResponse(
            total_records=total,
            loaded_count=loaded,
            rejected_count=len(rejected_rows),
            rejected_records=rejected_rows,
        )
    except Exception as exc:
        logger.error("Error reading data quality: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve data quality audit records.",
        )


@app.post("/api/ask", response_model=AskResponse)
def ask_question(payload: AskRequest) -> AskResponse:
    """Process natural language question into verified analytical answers."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty.",
        )

    if len(question) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question exceeds maximum allowed length of 500 characters.",
        )

    llm_client: GeminiLLMClient = app_state.get("llm_client")
    extraction, mode = route_question(question, llm_client)

    data_notes = (
        "Analysis computed over 48 valid Completed transactions. "
        "3 records excluded by quarantine: TXN0033 (returned), TXN0034 (zero quantity), TXN0051 (missing unit price)."
    )

    # Handle unsupported questions
    if extraction.intent == INTENT_UNSUPPORTED or extraction.intent not in WHITELISTED_INTENTS:
        return AskResponse(
            question=question,
            intent=INTENT_UNSUPPORTED,
            params={},
            answer=UNSUPPORTED_GUIDANCE_MESSAGE,
            supporting_data=[],
            sql="-- No SQL executed for unsupported question.",
            mode=mode,
            data_notes=data_notes,
        )

    # Execute parameterized query template against read-only database
    try:
        conn = get_read_only_conn(DB_PATH)
        handler = QUERY_HANDLERS[extraction.intent]
        metrics, supporting_data, sql = handler(conn, extraction.params)
        conn.close()
    except ValueError as val_err:
        # Handled domain error (e.g., month with no data)
        return AskResponse(
            question=question,
            intent=extraction.intent,
            params=extraction.params,
            answer=str(val_err),
            supporting_data=[],
            sql="-- Query aborted due to invalid parameter.",
            mode=mode,
            data_notes=data_notes,
        )
    except Exception as exc:
        logger.error("Query execution error for question '%s': %s", question, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while evaluating your question. Please check server logs.",
        )

    # Use handler-produced verified answer and verify LLM summary against hallucinations
    verified_answer = metrics.get("answer", "Query executed successfully.")
    final_answer = verify_or_replace_summary(extraction.summary, metrics, verified_answer)

    return AskResponse(
        question=question,
        intent=extraction.intent,
        params=extraction.params,
        answer=final_answer,
        supporting_data=supporting_data,
        sql=sql,
        mode=mode,
        data_notes=data_notes,
    )


# Serve static web frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_index():
    """Serve single-page frontend application."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Frontend index.html is being prepared."}
