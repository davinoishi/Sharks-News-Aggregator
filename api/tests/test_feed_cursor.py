"""Pure-logic tests for feed keyset cursors (brief 04, P3). No DB needed."""
from datetime import datetime, timezone

from app.core.queries import encode_cursor, decode_cursor


def test_cursor_round_trip():
    now = datetime.now(timezone.utc)
    assert decode_cursor(encode_cursor(now, 42)) == (now, 42)


def test_cursor_tolerates_absent_legacy_and_garbage():
    assert decode_cursor(None) is None
    assert decode_cursor("") is None
    assert decode_cursor("100") is None          # legacy numeric offset → ignored
    assert decode_cursor("not-base64!!") is None  # unparseable → ignored
