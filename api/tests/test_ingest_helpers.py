"""Tests for ingest text/feed helpers (brief 06)."""
import time
from datetime import timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import IngestMethod, Source, SourceCategory
from app.tasks.ingest import (
    ingest_api,
    ingest_html,
    parse_published_date,
    sanitize_feed_xml,
    strip_html,
)

# --- strip_html --------------------------------------------------------------

def test_strip_html_removes_tags():
    assert strip_html("<b>Celebrini</b> scores") == "Celebrini scores"


def test_strip_html_unescapes_entities():
    assert strip_html("Sharks &amp; Kings") == "Sharks & Kings"


def test_strip_html_strips_whitespace():
    assert strip_html("  <i>hi</i>  ") == "hi"


def test_strip_html_passthrough_none_and_empty():
    assert strip_html(None) is None
    assert strip_html("") == ""


# --- sanitize_feed_xml -------------------------------------------------------

def test_sanitize_replaces_named_entities():
    out = sanitize_feed_xml(b"<title>A&nbsp;B&mdash;C</title>")
    assert b"&#160;" in out
    assert b"&#8212;" in out
    assert b"&nbsp;" not in out


def test_sanitize_removes_control_chars():
    out = sanitize_feed_xml(b"good\x00\x07text")
    assert out == b"goodtext"


def test_sanitize_keeps_tab_newline_cr():
    assert sanitize_feed_xml(b"a\tb\nc\r") == b"a\tb\nc\r"


def test_sanitize_handles_non_utf8():
    # latin-1 'é' (0xe9) should decode and re-encode as utf-8 without raising.
    out = sanitize_feed_xml(b"caf\xe9")
    assert out.decode("utf-8") == "café"


# --- parse_published_date ----------------------------------------------------

def test_parse_published_uses_published_parsed():
    st = time.struct_time((2026, 6, 1, 12, 0, 0, 0, 0, -1))
    entry = SimpleNamespace(published_parsed=st)
    dt = parse_published_date(entry)
    assert dt is not None and dt.year == 2026 and dt.month == 6 and dt.day == 1


def test_parse_published_falls_back_to_updated():
    st = time.struct_time((2026, 1, 2, 0, 0, 0, 0, 0, -1))
    entry = SimpleNamespace(published_parsed=None, updated_parsed=st)
    dt = parse_published_date(entry)
    assert dt is not None and dt.year == 2026 and dt.month == 1 and dt.day == 2


def test_parse_published_is_timezone_aware():
    # brief 07, C2: parsed dates are returned as timezone-aware UTC.
    st = time.struct_time((2026, 6, 1, 12, 0, 0, 0, 0, -1))
    dt = parse_published_date(SimpleNamespace(published_parsed=st))
    assert dt.tzinfo is not None and dt.utcoffset() == timezone.utc.utcoffset(None)


def test_parse_published_none_when_absent():
    assert parse_published_date(SimpleNamespace()) is None


# --- unimplemented ingest methods mark the source broken (brief 07, C3) -------

def _source_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Source.__table__])
    return sessionmaker(bind=engine)()


def _make_source(db):
    src = Source(
        name="HTML scrape source",
        category=SourceCategory.OTHER,
        ingest_method=IngestMethod.HTML,
        base_url="https://example.com",
        fetch_error_count=0,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


def test_ingest_html_marks_source_broken():
    db = _source_session()
    try:
        src = _make_source(db)
        result = ingest_html(db, src)
        assert result["status"] == "error"
        assert "not_implemented" in result["reason"]
        # health == "broken" once fetch_error_count >= 3 (see admin /sources)
        assert src.fetch_error_count >= 3
    finally:
        db.close()


def test_ingest_api_marks_source_broken():
    db = _source_session()
    try:
        src = _make_source(db)
        result = ingest_api(db, src)
        assert result["status"] == "error"
        assert src.fetch_error_count >= 3
    finally:
        db.close()
