"""Defense-in-depth SQL validation guard.

Ensures that any SQL intended for execution is strictly a single, read-only SELECT statement.
Prevents statement chaining (;), comments, and data/schema manipulation keywords.
"""

import re


class SQLSecurityError(ValueError):
    """Raised when an executed query violates security constraints."""
    pass


FORBIDDEN_KEYWORDS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bPRAGMA\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bVACUUM\b",
    r"\bREPLACE\b",
    r"\bTRANSACTION\b",
    r"\bCOMMIT\b",
    r"\bROLLBACK\b",
    r"\bTRUNCATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bSAVEPOINT\b",
]

FORBIDDEN_PATTERNS = [re.compile(kw, re.IGNORECASE) for kw in FORBIDDEN_KEYWORDS]


def validate_safe_query(sql: str) -> None:
    """Validate that the given SQL string is strictly a single SELECT statement.
    
    Raises:
        SQLSecurityError: If the statement contains destructive commands, chaining, or comments.
    """
    if not sql or not isinstance(sql, str):
        raise SQLSecurityError("Query must be a non-empty string.")

    cleaned = sql.strip()

    # Disallow statement chaining with semicolons
    if ";" in cleaned:
        raise SQLSecurityError("Semicolons and chained SQL statements are strictly forbidden.")

    # Disallow SQL comments (prevent bypass tricks)
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise SQLSecurityError("SQL comments (-- or /* */) are strictly forbidden.")

    # Must begin strictly with SELECT (or read-only CTE WITH)
    first_token_match = re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE)
    if not first_token_match:
        raise SQLSecurityError("Only SELECT queries are permitted.")

    # Disallow destructive or schema-modifying keywords anywhere in query
    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            forbidden_word = match.group(0).upper()
            raise SQLSecurityError(f"Forbidden keyword '{forbidden_word}' detected in query.")


def is_safe_query(sql: str) -> bool:
    """Check if query passes safety checks without throwing an exception."""
    try:
        validate_safe_query(sql)
        return True
    except SQLSecurityError:
        return False
