"""Tests for maintenance cleanup helpers (scoreboard-stub removal, purge).

Postgres-only: clusters/story_variants use ARRAY columns.
"""
import os
from datetime import datetime, timedelta

import pytest

from app.models import (
    BlueSkyPost,
    Cluster,
    ClusterVariant,
    EventType,
    IngestMethod,
    PostStatus,
    RawItem,
    Source,
    SourceCategory,
    StoryVariant,
)
from app.tasks.maintenance import run_purge_old_items, run_scoreboard_stub_cleanup

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="requires PostgreSQL (clusters/story_variants use ARRAY columns)",
)

_n = 0


def _seed_story(db, source, title, event_type=EventType.GAME, when=None):
    """Create a raw_item + story_variant + cluster chain for one article."""
    global _n
    _n += 1
    url = f"https://src.example.com/cleanup-{_n}"
    when = when or datetime.utcnow()

    raw = RawItem(
        source_id=source.id,
        original_url=url,
        canonical_url=url,
        raw_title=title,
        created_at=when,
    )
    db.add(raw)
    db.flush()

    variant = StoryVariant(
        raw_item_id=raw.id,
        source_id=source.id,
        url=url,
        title=title,
        published_at=when,
        tokens=[],
        entities=[],
        event_type=event_type,
    )
    db.add(variant)
    db.flush()

    cluster = Cluster(
        headline=title,
        event_type=event_type,
        first_seen_at=when,
        last_seen_at=when,
        source_count=1,
        tokens=[],
        entities_agg=[],
    )
    db.add(cluster)
    db.flush()
    db.add(
        ClusterVariant(cluster_id=cluster.id, variant_id=variant.id, similarity_score=1.0)
    )
    # Every cluster gets a bluesky_posts row on prod (posted or skipped).
    # Its not-null cluster_id is what broke ORM-level cluster deletes.
    db.add(BlueSkyPost(cluster_id=cluster.id, status=PostStatus.SKIPPED))
    db.commit()
    return raw.id, cluster.id


def test_cleanup_removes_stub_items_and_their_clusters(pg_db):
    source = Source(
        name="Cleanup Src",
        category=SourceCategory.PRESS,
        ingest_method=IngestMethod.RSS,
        base_url="https://src.example.com",
    )
    pg_db.add(source)
    pg_db.flush()

    stub_raw_id, stub_cluster_id = _seed_story(
        pg_db,
        source,
        "Florida Panthers vs. San Jose Sharks Live Updates, Score, and Play-by-play - October 1, 2026",
    )
    # Streaming-promo stub caught by the WATCH_VS_TITLE_RE pattern (no marker).
    fubo_raw_id, fubo_cluster_id = _seed_story(
        pg_db,
        source,
        "Watch Dallas Stars vs San Jose Sharks - Fubo",
    )
    real_raw_id, real_cluster_id = _seed_story(
        pg_db,
        source,
        "Sharks Hire Jeff Kealty as Assistant General Manager",
        EventType.SIGNING,
    )

    result = run_scoreboard_stub_cleanup(pg_db)

    assert result["raw_items_deleted"] == 2
    assert result["clusters_deleted"] == 2
    assert pg_db.query(RawItem).filter(RawItem.id == stub_raw_id).first() is None
    assert pg_db.query(Cluster).filter(Cluster.id == stub_cluster_id).first() is None
    assert pg_db.query(RawItem).filter(RawItem.id == fubo_raw_id).first() is None
    assert pg_db.query(Cluster).filter(Cluster.id == fubo_cluster_id).first() is None
    # The legitimate article is untouched.
    assert pg_db.query(RawItem).filter(RawItem.id == real_raw_id).first() is not None
    assert pg_db.query(Cluster).filter(Cluster.id == real_cluster_id).first() is not None


def test_cleanup_noop_when_no_stubs(pg_db):
    result = run_scoreboard_stub_cleanup(pg_db)
    assert result["raw_items_deleted"] == 0


def test_purge_deletes_old_raw_items_with_variants(pg_db):
    # Regression: the ORM-level delete tried to NULL the not-null
    # story_variants.raw_item_id FK instead of letting the database cascade,
    # so any raw_item that had been enriched aborted the daily purge with an
    # IntegrityError.
    source = Source(
        name="Purge Src",
        category=SourceCategory.PRESS,
        ingest_method=IngestMethod.RSS,
        base_url="https://src.example.com",
    )
    pg_db.add(source)
    pg_db.flush()

    old = datetime.utcnow() - timedelta(days=45)
    old_raw_id, old_cluster_id = _seed_story(
        pg_db, source, "Sharks drop preseason opener", when=old
    )
    new_raw_id, _ = _seed_story(pg_db, source, "Sharks name new captain")

    result = run_purge_old_items(pg_db)

    assert result["raw_items_deleted"] == 1
    assert result["clusters_deleted"] == 1
    assert pg_db.query(RawItem).filter(RawItem.id == old_raw_id).first() is None
    assert pg_db.query(Cluster).filter(Cluster.id == old_cluster_id).first() is None
    assert pg_db.query(RawItem).filter(RawItem.id == new_raw_id).first() is not None
