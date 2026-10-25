# AI Usage Reflection

*A first-person developer reflection on building the Mini AI Business Intelligence Assistant with AI pair programming tools.*

---

## 🛠️ AI Tools Used
During the development of this project, I used:
- **Google Antigravity IDE** paired with **Gemini 2.5 Flash / Gemini 3.8 Flash** as my primary agentic AI pair programmer.
- The **Google GenAI Python SDK (`google-genai`)** to integrate Gemini directly as our runtime intent classifier.

---

## 💡 How I Used AI During Development
1. **Architecture & Intent Design**: I used the AI assistant to brainstorm and formalize the agentic tool-calling architecture. Instead of relying on open-ended text-to-SQL, we deliberately constrained the LLM to return strict JSON matching five pre-defined business intents.
2. **Schema & Contract Scaffolding**: I leveraged the AI to rapidly write the Pydantic schemas, database models, and SQL guard rules, ensuring complete type hinting and clean docstrings across all files.
3. **Automated Test Generation**: The AI helped write a comprehensive test suite of 24 unit and integration tests, including edge cases like prompt injections, malformed LLM responses, and month self-comparisons.
4. **Data Reconciliation**: I used the AI to write an independent pandas validation script that mathematically verified every calculation against the SQLite database down to the cent.

---

## 🐛 Real Problems Encountered & How I Debugged Them
1. **Windows Package Management & Privilege Boundaries**:
   - *Problem*: Attempting to install Python via `winget` triggered Windows UAC administrative prompts and failed with exit code 50 in headless shell execution.
   - *Fix*: I pivoted to Astral's `uv` toolchain, which installs into the local user space (`~/.local/bin`) without requiring administrative elevation, allowing seamless installation of CPython 3.11.17 and reproducible dependency management.
2. **Portable MinGit Execution Context**:
   - *Problem*: Attempting to copy `git.exe` alone into a separate bin folder triggered a `BUG (fork bomb)` error because MinGit requires its relative directory structure (`cmd`, `usr/bin`, `mingw64`).
   - *Fix*: I referenced the MinGit binary directly from its intact extraction directory (`$HOME\.local\mingit\cmd\git.exe`), preventing the recursion bug.
3. **Mock Client Exception Handling in the Router**:
   - *Problem*: During pytest execution, a test designed to verify LLM timeout fallback failed because the mock threw a direct `TimeoutError` that bypassed our outer exception handling in `router.py`.
   - *Fix*: I wrapped the LLM call inside `router.py` in an explicit `try-except Exception` block, ensuring that any unhandled exception or third-party client failure gracefully activates the deterministic regex router.
4. **Anti-Hallucination Number Verification**:
   - *Problem*: The LLM might generate a plausible-sounding summary that slightly misstates a percentage or rounds an order count incorrectly.
   - *Fix*: I engineered an anti-hallucination verification function (`verify_or_replace_summary`) that extracts all numbers from candidate summaries, checks them against the actual query result metrics, and replaces any mismatch with our verified template answer.

---

## 🚀 What I Would Improve With Another Day
If given an additional day to enhance this solution, I would implement:
1. **Retrieval-Augmented Generation (RAG) over Data Dictionary**: Embed documentation and column business definitions using vector search (e.g., ChromaDB) so the assistant can answer contextual questions like *"What does Discount_amount represent?"* or *"Why are returned orders excluded from revenue?"*.
2. **Multi-Turn Conversation Memory**: Maintain session context so users can ask follow-up questions (e.g., *"What about in the South region?"* following a total revenue query).
3. **Semantic Caching**: Cache classified intents and query results using Redis to deliver sub-millisecond responses for repeated questions without re-invoking the LLM.
4. **Containerization & CI/CD**: Provide a lightweight `Dockerfile` and GitHub Actions workflow running `pytest`, `ruff`, and `mypy` on every push.
5. **Secure Role-Based Text-to-SQL with Human-in-the-Loop**: For complex ad-hoc queries beyond the 5 fixed intents, introduce a sandboxed read-only database user with strict row and timeout limits, displaying query plans for user confirmation before execution.
