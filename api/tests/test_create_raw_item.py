"""Tests for create_raw_item dedup + age gate (brief 06).

Runs on sqlite — RawItem/Source have no ARRAY columns.
"""
from datetime import datetime, timedelta

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
