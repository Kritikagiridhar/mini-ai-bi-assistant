# Viva & Technical Interview Cheat-Sheet: Mini AI BI Assistant

A concise reference guide on the architecture, technical trade-offs, and 8 most probable interview questions for graduate engineer trainees.

---

## 🏛️ 1-Page Architecture Summary

```
[Business User] 
       │ (Natural language question)
       ▼
[FastAPI Gateway] ── (Input validator: length <= 500, non-empty)
       │
       ▼
[Intent Router (Dual Engine)]
   ├─► Engine 1: Google Gemini 2.5 Flash (Strict JSON Schema)
   └─► Engine 2: Deterministic Regex/Keyword Matcher (Zero-dependency fallback)
       │
       ▼
[Parameter Normalization & Pydantic Validation] (YYYY-MM, Title Case)
       │
       ▼
[Security Gate: sql_guard.py] (AST/Regex checks: Single SELECT only, no ;, comments, or mutations)
       │
       ▼
[Query Engine: queries.py] (Audited parameterized SQL templates)
       │
       ▼
[Storage: SQLite via mode=ro URI] (OS-enforced filesystem read-only connection)
       │
       ▼
[Anti-Hallucination Guard] (Verifies all numbers in LLM summary against SQL metrics)
       │
       ▼
[Frontend Dashboard / JSON Response] (Chart.js visualization, raw table, SQL breakdown)
```

### Key Pillars:
1. **Safety First**: The LLM only interprets natural language into structured parameters. It *never* writes SQL.
2. **Deterministic Correctness**: All calculations happen inside SQLite and Python; no hallucinated mathematical outputs.
3. **Data Quality Quarantine**: Generic ingestion isolates invalid data (`TXN0033` returned, `TXN0034` zero qty, `TXN0051` missing price) into `rejected_records`.
4. **Dual-Mode Availability**: Operates seamlessly in `mode="llm"` or `mode="fallback"`.

---

## 🎯 8 Most Likely Interview Questions & Sample Answers

### Q1: What makes this an "Agentic Tool-Calling" system rather than standard text-to-SQL?
> **Answer**: 
> In standard text-to-SQL, the LLM generates arbitrary SQL code from scratch. That introduces serious vulnerabilities: SQL injection, unindexed full-table scans, destructive commands, or subtle syntax bugs. 
> In our agentic tool-calling architecture, the LLM acts as an **intent router**. It is constrained to choose one of five whitelisted tools (queries) and extract validated parameters into a strict JSON schema. The application code retains full control over the SQL queries that actually execute.

---

### Q2: Why choose intent routing over free-form text-to-SQL for a Business Intelligence tool?
> **Answer**: 
> In business intelligence, **mathematical correctness and trust** are paramount. A financial metric that is 2% off due to an LLM hallucination is worse than no answer. By using pre-audited, parameterized SQL templates, we guarantee:
> 1. Exact, reproducible figures.
> 2. Zero risk of data mutation or SQL injection.
> 3. Sub-millisecond execution times using pre-indexed columns.
> 4. Graceful handling of edge cases (e.g., MoM baseline calculations).

---

### Q3: How does this approach compare to Retrieval-Augmented Generation (RAG)?
> **Answer**: 
> - **RAG** excels at unstructured textual data (e.g., policies, manuals, FAQs) by retrieving relevant text chunks using vector similarity. However, RAG fails at structured numeric aggregation (e.g., *"What is total revenue for Q1?"*) because vector similarity cannot compute sums or filter database rows.
> - **Our Approach (Structured Tool-Calling)** is designed specifically for tabular, quantitative data. It converts intent into structured filters and executes real database aggregations. 
> - *Ideal hybrid*: Use our tool-calling architecture for data queries, and layer RAG on top for business definitions and data dictionary questions.

---

### Q4: How do you guarantee that the LLM does not hallucinate numbers in its natural language summary?
> **Answer**: 
> We implement a multi-layered verification strategy:
> 1. The database query executes first and computes verified ground-truth metrics.
> 2. Our `verify_or_replace_summary()` guard parses all numeric tokens, currencies, and percentages from the candidate summary.
> 3. It checks every number against the set of ground-truth query metrics.
> 4. If any number diverges, the candidate summary is immediately rejected and replaced with our deterministic template string.

---

### Q5: What security measures prevent SQL injection and prompt injection?
> **Answer**: 
> We enforce defense-in-depth across 4 layers:
> 1. **Schema Whitelisting**: Prompt injection text cannot alter the fixed enum of 5 allowed intents.
> 2. **Parameterized Queries**: All user inputs are passed as parameters (`:product`, `:year_month`), never concatenated into SQL strings.
> 3. **`sql_guard.py`**: Validates that any SQL intended for execution is strictly a single `SELECT` statement and rejects semicolons, comments, and keywords like `DROP`, `DELETE`, `UPDATE`, or `ATTACH`.
> 4. **Read-Only SQLite URI**: The database connection is opened with `file:sales.db?mode=ro`, meaning write attempts are blocked at the SQLite engine level.

---

### Q6: How did you handle data cleaning and data anomalies?
> **Answer**: 
> Rather than hardcoding specific transaction IDs, we built a **generic data quality validation engine** in `loader.py`:
> - It enforces strict types: dates must parse via `dayfirst=True`, quantities must be positive integers ($>0$), and unit prices must be non-null and $>0$.
> - It isolates non-compliant records (`TXN0033` returned, `TXN0034` zero qty, `TXN0051` missing price) into a dedicated `rejected_records` quarantine table with exact audit reasons.
> - Clean records are loaded into `sales` and indexed. Both the API and UI expose this audit trail via `/api/data-quality`.

---

### Q7: What happens when the LLM service is down, rate-limited, or misconfigured?
> **Answer**: 
> The application never crashes (no 500 error). We built a **dual-mode router**:
> - If `GEMINI_API_KEY` is missing or the API call times out / throws an exception, the system catches it, logs a warning, and activates our deterministic regex/keyword fallback router.
> - The API response returns `"mode": "fallback"` to maintain complete transparency with the user and UI while answering the question accurately.

---

### Q8: How would you scale this architecture to support millions of rows and hundreds of concurrent users?
> **Answer**: 
> 1. **Database Migration**: Move from SQLite to an analytical columnar database like **PostgreSQL with TimescaleDB / ClickHouse / Snowflake**, which are optimized for OLAP aggregations.
> 2. **Connection Pooling & Read Replicas**: Distribute queries across read-only database replicas using PgBouncer.
> 3. **Semantic Query Caching**: Cache common query results in Redis using normalized intent hashes as cache keys (e.g., `total_revenue:2026-03`).
> 4. **Async LLM Pipeline**: Use async HTTP client pools to call Gemini without blocking worker threads.
> 5. **Materialized Aggregation Views**: Pre-compute daily and monthly revenue rollups so queries scan pre-aggregated summaries instead of raw transaction tables.
