"""Shared request-parsing helpers (brief 07, Q3).

Extracted from ``app.main`` so multiple routers can share them.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException

from app.core.datetime_utils import utcnow


def parse_since_parameter(since: Optional[str]) -> Optional[datetime]:
    """
    Parse the 'since' parameter into a datetime.

    Accepts:
    - '24h', '7d', '30d' (relative times)
    - ISO 8601 timestamp (absolute time)

    Relative values are resolved against timezone-aware UTC "now" (C2), so the
    returned datetime is aware and compares cleanly with the TIMESTAMPTZ columns.
    """
    if not since:
        return None

    # Relative time shortcuts
    if since.endswith('h'):
        hours = int(since[:-1])
        return utcnow() - timedelta(hours=hours)
    elif since.endswith('d'):
        days = int(since[:-1])
        return utcnow() - timedelta(days=days)
    else:
        # Try parsing as ISO timestamp
        try:
            return datetime.fromisoformat(since.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'since' parameter")


def parse_llm_approved(llm_response: Optional[str]) -> bool:
    """Interpret a stored LLM relevance response as an approve/reject boolean."""
    if not llm_response:
        return False
    resp = llm_response.strip()
    # JSON format from OpenRouter: {"relevant": true, ...}
    if '"relevant"' in resp:
        return '"relevant": true' in resp.lower() or '"relevant":true' in resp.lower()
    # Legacy Ollama format: "YES ..." or "DECISION: YES"
    return resp.upper().startswith("YES") or "DECISION: YES" in resp.upper()


# Backwards-compatible alias: this helper was previously a private name in
# app.main and is imported as such by the test suite.
_parse_llm_approved = parse_llm_approved
