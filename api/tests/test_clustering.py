"""Integration tests for match_or_create_cluster (brief 06).

Postgres-only: clusters/story_variants use ARRAY columns. Drives the real
clustering function with seeded variants and asserts merge/no-merge outcomes.
"""
import os
from datetime import datetime, timedelta

import pytest

from app.models import EventType, IngestMethod, RawItem, Source, SourceCategory, StoryVariant
from app.tasks.enrich import match_or_create_cluster, normalize_tokens

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="requires PostgreSQL (clusters/story_variants use ARRAY columns)",
)

_n = 0


def _source(db):
    s = Source(
        name="Src",
        category=SourceCategory.PRESS,
        ingest_method=IngestMethod.RSS,
        base_url="https://src.example.com",
    )
    db.add(s)
    db.flush()
    return s


def _variant(db, source, title, published_at, event_type="signing"):
    global _n
    _n += 1
    url = f"https://src.example.com/{_n}"
    raw = RawItem(source_id=source.id, original_url=url, canonical_url=url, raw_title=title)
    db.add(raw)
    db.flush()
    v = StoryVariant(
        raw_item_id=raw.id,
        source_id=source.id,
        url=url,
        title=title,
        published_at=published_at,
        tokens=normalize_tokens(title),
        entities=[],
        event_type=EventType(event_type),
    )
    db.add(v)
    db.flush()
    return v


def _cluster(db, source, title, published_at, event_type="signing"):
    v = _variant(db, source, title, published_at, event_type)
    return match_or_create_cluster(db, v, v.tokens, [], event_type, source, tag_names=[])


def test_same_story_two_sources_merge_into_one_cluster(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    title = "Celebrini signs eight year extension with the Sharks"
    cid1 = _cluster(pg_db, src, title, now)
    cid2 = _cluster(pg_db, src, title, now)  # syndicated copy → title match
    assert cid1 == cid2


def test_unrelated_stories_do_not_merge(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(pg_db, src, "Celebrini signs eight year extension", now, "signing")
    cid2 = _cluster(pg_db, src, "Prospect drafted in third round shows promise", now, "prospect")
    assert cid1 != cid2


def test_game_articles_cluster_by_game_id(pg_db):
    src = _source(pg_db)
    # Must be within the 24h game window, so use "now" (same instant → same date).
    now = datetime.utcnow()
    cid1 = _cluster(pg_db, src, "Sharks fall to Boston 4-2", now, "game")
    cid2 = _cluster(pg_db, src, "Recap: San Jose drops contest against the Bruins", now, "game")
    assert cid1 == cid2  # same opponent (BOS) + same date → same game id


def test_time_window_respected(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    title = "Karlsson trade rumors continue to swirl"
    # First cluster is created ~100h ago — outside the 72h 'trade' window.
    cid_old = _cluster(pg_db, src, title, now - timedelta(hours=100), "trade")
    # An identical-title article today must NOT join the out-of-window cluster.
    cid_new = _cluster(pg_db, src, title, now, "trade")
    assert cid_old != cid_new
