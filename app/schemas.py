"""Pydantic schemas and models for the API and intent router."""

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    """Incoming user question request."""
    question: str = Field(
        ...,
        description="Natural language business question (max 500 characters).",
        min_length=1,
        max_length=500,
    )

    @field_validator("question")
    @classmethod
    def validate_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Question cannot be empty or whitespace only.")
        return trimmed


class IntentParams(BaseModel):
    """Optional parameters extracted from question."""
    product: Optional[str] = None
    category: Optional[str] = None
    region: Optional[str] = None
    sales_channel: Optional[str] = None
    year_month: Optional[str] = None
    month_a: Optional[str] = None
    month_b: Optional[str] = None


class IntentExtraction(BaseModel):
    """Strict structure produced by router / LLM."""
    intent: str
    params: dict[str, Any] = Field(default_factory=dict)
    summary: Optional[str] = None


class AskResponse(BaseModel):
    """Standardized API response for questions."""
    question: str
    intent: str
    params: dict[str, Any]
    answer: str
    supporting_data: list[dict[str, Any]]
    sql: str
    mode: str  # "llm" or "fallback"
    data_notes: str


class RejectedRecord(BaseModel):
    """Information regarding a quarantined record."""
    transaction_id: Optional[str] = None
    row_data: Optional[str] = None
    reason: str
    rejected_at: Optional[str] = None


class DataQualityResponse(BaseModel):
    """Data quality and quarantine audit."""
    total_records: int
    loaded_count: int
    rejected_count: int
    rejected_records: list[dict[str, Any]]


class HealthResponse(BaseModel):
    """Service health check."""
    status: str
    database: str
    loaded_count: int
    rejected_count: int
