"""Intent router with dual-engine support: LLM classification and deterministic regex fallback.

Includes parameter normalization and anti-hallucination number verification.
"""

import logging
import re
from typing import Any, Optional

from app.intents import (
    DEFAULT_YEAR,
    INTENT_COMPARE_MONTHS,
    INTENT_MONTHLY_REVENUE_TREND,
    INTENT_TOP_PRODUCT_BY_REVENUE,
    INTENT_TOP_REGION_BY_SALES,
    INTENT_TOTAL_REVENUE,
    INTENT_UNSUPPORTED,
    VALID_CHANNELS,
    VALID_MONTHS,
    VALID_REGIONS,
    WHITELISTED_INTENTS,
)
from app.llm_client import GeminiLLMClient
from app.schemas import IntentExtraction

logger = logging.getLogger(__name__)

MONTH_NAME_MAP = {
    "january": "2026-01",
    "jan": "2026-01",
    "february": "2026-02",
    "feb": "2026-02",
    "march": "2026-03",
    "mar": "2026-03",
    "april": "2026-04",
    "apr": "2026-04",
    "may": "2026-05",
    "june": "2026-06",
    "jun": "2026-06",
    "july": "2026-07",
    "jul": "2026-07",
    "august": "2026-08",
    "aug": "2026-08",
    "september": "2026-09",
    "sep": "2026-09",
    "october": "2026-10",
    "oct": "2026-10",
    "november": "2026-11",
    "nov": "2026-11",
    "december": "2026-12",
    "dec": "2026-12",
}


def normalize_month(value: Optional[str]) -> Optional[str]:
    """Normalize user or LLM month representation to ISO YYYY-MM.
    
    Examples:
        'March' -> '2026-03'
        'mar 2026' -> '2026-03'
        '2026-03' -> '2026-03'
        '03-2026' -> '2026-03'
    """
    if not value or not isinstance(value, str):
        return None

    cleaned = value.strip().lower()

    # Pattern: YYYY-MM
    iso_match = re.search(r"\b(202\d)-(0[1-9]|1[0-2])\b", cleaned)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}"

    # Pattern: MM-YYYY or MM/YYYY
    my_match = re.search(r"\b(0[1-9]|1[0-2])[-/](202\d)\b", cleaned)
    if my_match:
        return f"{my_match.group(2)}-{my_match.group(1)}"

    # Match named months e.g. "March", "mar 2026"
    for name, iso_str in MONTH_NAME_MAP.items():
        if re.search(rf"\b{name}\b", cleaned):
            year_match = re.search(r"\b(202\d)\b", cleaned)
            year = year_match.group(1) if year_match else DEFAULT_YEAR
            month_part = iso_str.split("-")[1]
            return f"{year}-{month_part}"

    return None


def normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Clean and standardize parameter values against allowed domain entities."""
    clean: dict[str, Any] = {}
    if not isinstance(params, dict):
        return clean

    # Month params
    if params.get("year_month"):
        norm_ym = normalize_month(str(params["year_month"]))
        if norm_ym:
            clean["year_month"] = norm_ym

    if params.get("month_a"):
        norm_ma = normalize_month(str(params["month_a"]))
        if norm_ma:
            clean["month_a"] = norm_ma

    if params.get("month_b"):
        norm_mb = normalize_month(str(params["month_b"]))
        if norm_mb:
            clean["month_b"] = norm_mb

    # Region
    raw_region = params.get("region")
    if raw_region and isinstance(raw_region, str):
        for reg in VALID_REGIONS:
            if reg.lower() == raw_region.strip().lower():
                clean["region"] = reg
                break

    # Channel
    raw_channel = params.get("sales_channel") or params.get("channel")
    if raw_channel and isinstance(raw_channel, str):
        for chan in VALID_CHANNELS:
            if chan.lower() == raw_channel.strip().lower():
                clean["sales_channel"] = chan
                break

    # Product & Category
    if params.get("product"):
        clean["product"] = str(params["product"]).strip()
    if params.get("category"):
        clean["category"] = str(params["category"]).strip()

    return clean


def deterministic_fallback_match(question: str) -> IntentExtraction:
    """Regex and keyword-based deterministic intent router.
    
    Used when LLM API key is absent, times out, or returns invalid output.
    """
    q = question.lower().strip()

    # Injection or destructive keyword safeguard
    if any(k in q for k in ["drop table", "delete from", "insert into", "update sales", "alter table", "exec ", "--", ";"]):
        return IntentExtraction(intent=INTENT_UNSUPPORTED, params={})

    # 1. Compare Months
    # Look for patterns like "compare march and april", "march vs april", "compare 2026-03 and 2026-04"
    found_months = []
    # Check words against month dictionary
    tokens = re.findall(r"[a-z0-9\-]+", q)
    for token in tokens:
        norm = normalize_month(token)
        if norm and norm not in found_months:
            found_months.append(norm)

    is_compare_question = any(w in q for w in ["compare", "vs", "versus", "difference between", "growth between", "change between"])
    if is_compare_question and len(found_months) >= 2:
        return IntentExtraction(
            intent=INTENT_COMPARE_MONTHS,
            params={"month_a": found_months[0], "month_b": found_months[1]},
        )
    elif is_compare_question and len(found_months) == 1:
        # Edge case: self comparison or single month comparison
        return IntentExtraction(
            intent=INTENT_COMPARE_MONTHS,
            params={"month_a": found_months[0], "month_b": found_months[0]},
        )

    # 2. Monthly Revenue Trend
    if any(kw in q for kw in ["monthly trend", "revenue trend", "mom growth", "month over month", "revenue over time", "by month", "monthly revenue"]):
        return IntentExtraction(intent=INTENT_MONTHLY_REVENUE_TREND, params={})

    # 3. Top Region by Sales
    if any(kw in q for kw in ["top region", "best region", "highest sales region", "sales by region", "revenue by region", "which region", "regional sales"]):
        return IntentExtraction(intent=INTENT_TOP_REGION_BY_SALES, params={})

    # 4. Top Product by Revenue
    if any(kw in q for kw in ["top product", "top products", "best selling product", "highest revenue product", "best product", "popular product"]):
        params: dict[str, Any] = {}
        for reg in VALID_REGIONS:
            if re.search(rf"\b{reg.lower()}\b", q):
                params["region"] = reg
        if found_months:
            params["year_month"] = found_months[0]
        return IntentExtraction(intent=INTENT_TOP_PRODUCT_BY_REVENUE, params=params)

    # 5. Total Revenue
    if any(kw in q for kw in ["total revenue", "revenue", "sales", "how much revenue", "total sales", "overall revenue"]):
        params: dict[str, Any] = {}
        for reg in VALID_REGIONS:
            if re.search(rf"\b{reg.lower()}\b", q):
                params["region"] = reg
        for chan in VALID_CHANNELS:
            if re.search(rf"\b{chan.lower()}\b", q):
                params["sales_channel"] = chan
        if found_months:
            params["year_month"] = found_months[0]
        for cat in ["electronics", "accessories", "office supplies"]:
            if cat in q:
                params["category"] = cat.title()
        return IntentExtraction(intent=INTENT_TOTAL_REVENUE, params=params)

    # Unsupported default
    return IntentExtraction(intent=INTENT_UNSUPPORTED, params={})


def verify_or_replace_summary(
    candidate_summary: Optional[str],
    query_result_metrics: dict[str, Any],
    templated_answer: str,
) -> str:
    """Anti-hallucination verification.
    
    Verifies that every numeric value in the candidate summary matches
    a figure from the query result metrics. If any number diverges,
    falls back safely to the templated answer.
    """
    if not candidate_summary or not isinstance(candidate_summary, str):
        return templated_answer

    # Extract all numbers from candidate summary (ignoring $, %, commas)
    found_nums = re.findall(r"[\$]?\b\d+(?:,\d{3})*(?:\.\d+)?%?", candidate_summary)
    if not found_nums:
        # No numbers mentioned in summary
        return candidate_summary

    # Gather all valid reference numbers from query result metrics
    def collect_numbers(val: Any) -> list[float]:
        nums = []
        if isinstance(val, (int, float)):
            nums.append(round(float(val), 2))
        elif isinstance(val, dict):
            for v in val.values():
                nums.extend(collect_numbers(v))
        elif isinstance(val, list):
            for item in val:
                nums.extend(collect_numbers(item))
        return nums

    reference_nums = set(collect_numbers(query_result_metrics))
    # Add common date numbers (e.g. 2026, 1..12, 1..5 for ranks)
    reference_nums.update([2026.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

    for raw_num in found_nums:
        clean_num = raw_num.replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            val = round(float(clean_num), 2)
            # Allow small float tolerances
            matched = any(abs(val - ref) < 0.05 for ref in reference_nums)
            if not matched:
                logger.info(
                    "Anti-Hallucination Guard: Mismatch detected for '%s' (%f). Defaulting to templated answer.",
                    raw_num,
                    val,
                )
                return templated_answer
        except ValueError:
            continue

    return candidate_summary


def route_question(
    question: str, llm_client: Optional[GeminiLLMClient] = None
) -> tuple[IntentExtraction, str]:
    """Route natural language question to strict intent and params.
    
    Returns:
        (IntentExtraction, mode) where mode is "llm" or "fallback".
    """
    if llm_client and llm_client.is_available():
        try:
            llm_raw = llm_client.extract_intent(question)
            if llm_raw and isinstance(llm_raw, dict):
                intent = llm_raw.get("intent", "").strip().lower()
                if intent in WHITELISTED_INTENTS:
                    raw_params = llm_raw.get("params", {}) or {}
                    normalized = normalize_params(raw_params)
                    return (
                        IntentExtraction(
                            intent=intent,
                            params=normalized,
                            summary=llm_raw.get("summary"),
                        ),
                        "llm",
                    )
        except Exception as exc:
            logger.warning("LLM client encountered an exception; activating fallback: %s", exc)

    # Fallback to deterministic regex router
    extraction = deterministic_fallback_match(question)
    extraction.params = normalize_params(extraction.params)
    return extraction, "fallback"
