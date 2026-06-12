"""Shared request-parsing helpers (brief 07, Q3).

Extracted from ``app.main`` so multiple routers can share them.
"""
import json
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
    """Interpret a stored LLM relevance response as an approve/reject boolean.

    Current rows store JSON from OpenRouter (``{"relevant": true, ...}``), so we
    parse it properly with ``json.loads`` and read the ``relevant`` flag (brief
    09, C5). Only when the stored value isn't valid JSON do we fall back to the
    legacy substring/Ollama heuristics, which exist solely for old rows.
    """
    if not llm_response:
        return False
    resp = llm_response.strip()

    # Preferred path: the response is JSON with a "relevant" boolean.
    try:
        parsed = json.loads(resp)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    if isinstance(parsed, dict) and "relevant" in parsed:
        value = parsed["relevant"]
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "yes")
        return bool(value)

    # Legacy fallbacks for rows that predate JSON storage:
    # truncated JSON strings, and the old Ollama "YES"/"DECISION: YES" format.
    if '"relevant"' in resp:
        return '"relevant": true' in resp.lower() or '"relevant":true' in resp.lower()
    return resp.upper().startswith("YES") or "DECISION: YES" in resp.upper()


# Backwards-compatible alias: this helper was previously a private name in
# app.main and is imported as such by the test suite.
_parse_llm_approved = parse_llm_approved
