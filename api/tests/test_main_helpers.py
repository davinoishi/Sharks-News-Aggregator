"""Tests for main.py parsing helpers (brief 06)."""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.main import _parse_llm_approved, parse_since_parameter

# --- parse_since_parameter ---------------------------------------------------

def test_since_none():
    assert parse_since_parameter(None) is None


def test_since_hours():
    out = parse_since_parameter("24h")
    delta = datetime.utcnow() - out
    assert timedelta(hours=23, minutes=59) < delta < timedelta(hours=24, minutes=1)


def test_since_days():
    out = parse_since_parameter("7d")
    delta = datetime.utcnow() - out
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)


def test_since_iso_with_z():
    out = parse_since_parameter("2026-01-15T00:00:00Z")
    assert out.year == 2026 and out.month == 1 and out.day == 15


def test_since_garbage_raises_400():
    with pytest.raises(HTTPException) as exc:
        parse_since_parameter("not-a-date")
    assert exc.value.status_code == 400


# --- _parse_llm_approved -----------------------------------------------------

@pytest.mark.parametrize("resp,expected", [
    ('{"relevant": true, "confidence": "HIGH"}', True),
    ('{"relevant":true}', True),
    ('{"relevant": false}', False),
    ('{"relevant": TRUE}', True),       # case-insensitive match on "true"
    ("YES this is about the Sharks", True),
    ("DECISION: YES", True),
    ("NO not relevant", False),
    ("", False),
    (None, False),
])
def test_parse_llm_approved(resp, expected):
    assert _parse_llm_approved(resp) is expected
