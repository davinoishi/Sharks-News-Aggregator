"""Tests for create_raw_item dedup + age gate (brief 06).

Runs on sqlite — RawItem/Source have no ARRAY columns.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.models import IngestMethod, RawItem, Source, SourceCategory
from app.tasks.ingest import create_raw_item


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Source.__table__, RawItem.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def source(db):
    s = Source(
        name="Test Source",
        category=SourceCategory.PRESS,
        ingest_method=IngestMethod.RSS,
        base_url="https://test.example.com",
    )
    db.add(s)
    db.commit()
    return s


def test_creates_new_item(db, source):
    item = create_raw_item(db, source.id, "https://test.example.com/a", raw_title="A")
    assert item is not None
    assert db.query(RawItem).count() == 1


def test_empty_url_returns_none(db, source):
    assert create_raw_item(db, source.id, "", raw_title="A") is None
    assert db.query(RawItem).count() == 0


def test_dedup_by_canonical_url(db, source):
    create_raw_item(db, source.id, "https://test.example.com/a?utm_source=x", raw_title="A")
    # Same URL after tracking-param normalization → duplicate.
    dup = create_raw_item(db, source.id, "https://test.example.com/a?utm_source=y", raw_title="B")
    assert dup is None
    assert db.query(RawItem).count() == 1


def test_dedup_by_source_item_id(db, source):
    create_raw_item(db, source.id, "https://test.example.com/a", raw_title="A", source_item_id="guid-1")
    dup = create_raw_item(db, source.id, "https://test.example.com/different", raw_title="B", source_item_id="guid-1")
    assert dup is None
    assert db.query(RawItem).count() == 1


def test_dedup_by_same_source_title(db, source):
    create_raw_item(db, source.id, "https://test.example.com/a", raw_title="Same Headline")
    dup = create_raw_item(db, source.id, "https://test.example.com/b", raw_title="Same Headline")
    assert dup is None
    assert db.query(RawItem).count() == 1


def test_distinct_items_both_created(db, source):
    create_raw_item(db, source.id, "https://test.example.com/a", raw_title="Headline A")
    create_raw_item(db, source.id, "https://test.example.com/b", raw_title="Headline B")
    assert db.query(RawItem).count() == 2


def test_age_gate_rejects_old_articles(db, source):
    old = datetime.utcnow() - timedelta(days=settings.max_article_age_days + 1)
    item = create_raw_item(db, source.id, "https://test.example.com/old", raw_title="Old", published_at=old)
    assert item is None
    assert db.query(RawItem).count() == 0


def test_recent_article_passes_age_gate(db, source):
    recent = datetime.utcnow() - timedelta(days=1)
    item = create_raw_item(db, source.id, "https://test.example.com/new", raw_title="New", published_at=recent)
    assert item is not None


def test_verify_age_rejects_article_with_old_true_date(db, source, monkeypatch):
    """Feed says fresh, but the article's own metadata says it's years old."""
    import app.tasks.ingest as ingest

    old_true = datetime(2024, 6, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(ingest, "fetch_published_date", lambda url: old_true)

    fresh_feed_date = datetime.utcnow() - timedelta(hours=1)
    item = create_raw_item(
        db, source.id, "https://test.example.com/resurfaced",
        raw_title="Old news, fresh pubDate", published_at=fresh_feed_date,
        verify_age=True,
    )
    assert item is None
    assert db.query(RawItem).count() == 0


def test_verify_age_accepts_article_with_recent_true_date(db, source, monkeypatch):
    import app.tasks.ingest as ingest

    recent_true = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(ingest, "fetch_published_date", lambda url: recent_true)

    item = create_raw_item(
        db, source.id, "https://test.example.com/genuinely-new",
        raw_title="Real news", published_at=datetime.utcnow(),
        verify_age=True,
    )
    assert item is not None
    # The verified true date is stored, not the feed date. (SQLite drops tzinfo
    # on the stored column, so coerce back to aware UTC before comparing.)
    from app.core.datetime_utils import ensure_aware
    assert ensure_aware(item.published_at) == recent_true


def test_verify_age_rejects_undated_item(db, source, monkeypatch):
    """No feed date and no page date → reject rather than defaulting to now (D)."""
    import app.tasks.ingest as ingest

    monkeypatch.setattr(ingest, "fetch_published_date", lambda url: None)

    item = create_raw_item(
        db, source.id, "https://test.example.com/undated",
        raw_title="Undated", published_at=None, verify_age=True,
    )
    assert item is None
    assert db.query(RawItem).count() == 0


def test_verify_age_falls_back_to_feed_date_when_page_undated(db, source, monkeypatch):
    """Page date unknown but feed date is recent → keep the item on feed date."""
    import app.tasks.ingest as ingest

    monkeypatch.setattr(ingest, "fetch_published_date", lambda url: None)

    feed_date = datetime.utcnow() - timedelta(hours=3)
    item = create_raw_item(
        db, source.id, "https://test.example.com/feed-only",
        raw_title="Feed dated", published_at=feed_date, verify_age=True,
    )
    assert item is not None


def test_extract_published_date_from_meta_tag():
    from app.tasks.ingest import extract_published_date

    html = """
    <html><head>
      <meta property="article:published_time" content="2024-06-01T14:30:00Z">
    </head><body></body></html>
    """
    parsed = extract_published_date(html)
    assert parsed == datetime(2024, 6, 1, 14, 30, tzinfo=timezone.utc)


def test_extract_published_date_from_jsonld():
    from app.tasks.ingest import extract_published_date

    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type": "NewsArticle", "datePublished": "2025-01-15T09:00:00-05:00"}
      </script>
    </head><body></body></html>
    """
    parsed = extract_published_date(html)
    assert parsed == datetime(2025, 1, 15, 14, 0, tzinfo=timezone.utc)


def test_extract_published_date_missing_returns_none():
    from app.tasks.ingest import extract_published_date

    assert extract_published_date("<html><body>no date here</body></html>") is None
