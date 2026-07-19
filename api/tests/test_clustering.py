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


def _variant(db, source, title, published_at, event_type="signing", url=None):
    global _n
    _n += 1
    url = url or f"https://src.example.com/{_n}"
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


def _cluster(db, source, title, published_at, event_type="signing", url=None):
    v = _variant(db, source, title, published_at, event_type, url=url)
    return match_or_create_cluster(db, v, v.tokens, [], event_type, source, tag_names=[])


def test_same_story_two_sources_merge_into_one_cluster(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    title = "Celebrini signs eight year extension with the Sharks"
    cid1 = _cluster(pg_db, src, title, now)
    cid2 = _cluster(pg_db, src, title, now)  # syndicated copy → title match
    assert cid1 == cid2


@pytest.mark.parametrize("left,right,event_type", [
    (
        "Sharks news: San Jose signs former Rangers defenseman to one-year, two-way contract",
        "Sharks sign former Rangers defenseman to one-year, two-way contract - Yahoo Sports",
        "signing",
    ),
    (
        "BARRACUDA UPGRADE: Eric Comrie, Alex Barre-Boulet STRENGTHEN San Jose’s AHL PLAYOFF Push",
        "Eric Comrie, Alex Barre-Boulet STRENGTHEN San Jose's AHL PLAYOFF Push | cbs19.tv",
        "other",
    ),
    (
        # Rewritten headline for the same staff hire: "GM" vs "General
        # Manager" plus a dropped name. Merges via headline-to-headline
        # token overlap after abbreviation canonicalization.
        "Sharks Hire Jeff Kealty as Assistant General Manager",
        "Sharks Hire New Assistant GM - Yahoo Sports",
        "signing",
    ),
])
def test_reported_duplicate_pairs_merge_without_entities(
    pg_db, left, right, event_type
):
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(pg_db, src, left, now, event_type)
    cid2 = _cluster(pg_db, src, right, now, event_type)
    assert cid1 == cid2


def test_personnel_story_merges_across_event_types_via_shared_name(pg_db):
    # "Jeff Kealty" isn't in the entity table (staff, not roster), and the two
    # headlines disagree on event classification. The shared person-name bigram
    # plus moderate title overlap should still put them on one card.
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(
        pg_db, src,
        "Assistant GM Jeff Kealty departs Predators to pursue position with Sharks - Predlines",
        now, "other",
    )
    cid2 = _cluster(
        pg_db, src,
        "Sharks Hire Jeff Kealty as Assistant General Manager",
        now, "signing",
    )
    assert cid1 == cid2


def test_shared_name_alone_does_not_merge_different_stories(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(
        pg_db, src,
        "Jeff Kealty builds out Sharks scouting department with three hires",
        now, "signing",
    )
    cid2 = _cluster(
        pg_db, src,
        "Jeff Kealty attends Predators alumni charity golf event",
        now, "other",
    )
    assert cid1 != cid2


def test_late_copies_use_publication_relative_window(pg_db):
    src = _source(pg_db)
    old_publication_time = datetime.utcnow() - timedelta(days=5)
    title = "Sharks sign Libor Hajek to a one year contract"
    cid1 = _cluster(pg_db, src, title, old_publication_time, "signing")
    cid2 = _cluster(pg_db, src, title, old_publication_time, "signing")
    assert cid1 == cid2


def test_cross_domain_shared_content_uuid_merges(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    content_id = "535-646a692c-dca4-4e11-aa72-38891f6d78af"
    cid1 = _cluster(
        pg_db,
        src,
        "Barracuda roster analysis",
        now,
        "other",
        url=f"https://www.kens5.com/video/story/{content_id}",
    )
    cid2 = _cluster(
        pg_db,
        src,
        "AHL playoff push video",
        now,
        "prospect",
        url=f"https://www.fox61.com/video/story/{content_id}",
    )
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
