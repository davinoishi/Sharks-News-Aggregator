"""Tests for the brief-08 public endpoints: /entities, /rss, and the
``get_top_variant_urls`` helper that powers clickable headlines (U2/U3/U5).

The entity-search tests run on SQLite (the ``entities`` table has no ARRAY
columns). The cluster/variant tests need PostgreSQL — clusters/story_variants
use ARRAY columns SQLite can't create — so they skip unless DATABASE_URL points
at Postgres (same convention as test_feed_queries.py).
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import Entity
from app.routers.feed import list_entities

DB_URL = os.environ.get("DATABASE_URL", "")
requires_postgres = pytest.mark.skipif(
    not DB_URL.startswith("postgresql"),
    reason="requires PostgreSQL (clusters/story_variants use ARRAY columns)",
)


def _sqlite_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Entity.__table__])
    return sessionmaker(bind=engine)()


def test_entities_search_matches_case_insensitively():
    db = _sqlite_session()
    try:
        db.add_all([
            Entity(name="Macklin Celebrini", slug="macklin-celebrini", entity_type="player"),
            Entity(name="William Eklund", slug="william-eklund", entity_type="player"),
        ])
        db.commit()

        result = list_entities(query="celeb", limit=15, db=db)
        slugs = [e["slug"] for e in result["entities"]]
        assert slugs == ["macklin-celebrini"]
    finally:
        db.close()


def test_entities_empty_query_lists_alphabetically():
    db = _sqlite_session()
    try:
        db.add_all([
            Entity(name="Zeev", slug="zeev", entity_type="player"),
            Entity(name="Alpha", slug="alpha", entity_type="player"),
        ])
        db.commit()

        result = list_entities(query="", limit=15, db=db)
        names = [e["name"] for e in result["entities"]]
        assert names == ["Alpha", "Zeev"]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Postgres-backed helpers below.

@pytest.fixture
def pg():
    if not DB_URL.startswith("postgresql"):
        pytest.skip("requires PostgreSQL")
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine)
    conn = engine.connect()
    trans = conn.begin()
    session = sessionmaker(bind=conn)()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()
        engine.dispose()


_seq = 0


def _uniq(prefix):
    global _seq
    _seq += 1
    return f"{prefix}-{_seq}"


def _make_cluster_with_variants(db, variants):
    """variants: list of (category, published_at). Returns (cluster, urls-by-cat)."""
    from app.models import (
        Cluster,
        ClusterStatus,
        ClusterVariant,
        RawItem,
        Source,
        StoryVariant,
    )

    now = datetime.now(timezone.utc)
    cluster = Cluster(
        headline="Sharks make a move",
        first_seen_at=now,
        last_seen_at=now,
        status=ClusterStatus.ACTIVE,
        source_count=len(variants),
    )
    db.add(cluster)
    db.flush()

    urls = {}
    for category, published_at in variants:
        source = Source(
            name=_uniq("src"),
            category=category,
            ingest_method="rss",
            base_url=f"https://{_uniq('src')}.example.com",
        )
        db.add(source)
        db.flush()
        raw = RawItem(
            source_id=source.id,
            original_url=f"https://x.example.com/{_uniq('raw')}",
            raw_title="t",
        )
        db.add(raw)
        db.flush()
        url = f"https://{category}-{_uniq('v')}.example.com/story"
        variant = StoryVariant(
            raw_item_id=raw.id,
            source_id=source.id,
            url=url,
            title="t",
            published_at=published_at,
        )
        db.add(variant)
        db.flush()
        db.add(ClusterVariant(cluster_id=cluster.id, variant_id=variant.id))
        urls.setdefault(category, []).append(url)
    db.flush()
    return cluster, urls


@requires_postgres
def test_top_variant_url_prefers_official_over_press(pg):
    from app.core.queries import get_top_variant_urls

    now = datetime.now(timezone.utc)
    # Press is newer, but official should still win the ranking.
    cluster, urls = _make_cluster_with_variants(
        pg,
        [("press", now), ("official", now - timedelta(hours=2))],
    )

    result = get_top_variant_urls(pg, [cluster.id])
    assert result[cluster.id] == urls["official"][0]


@requires_postgres
def test_top_variant_url_breaks_ties_by_recency(pg):
    from app.core.queries import get_top_variant_urls

    now = datetime.now(timezone.utc)
    cluster, urls = _make_cluster_with_variants(
        pg,
        [("press", now - timedelta(hours=3)), ("press", now)],
    )

    result = get_top_variant_urls(pg, [cluster.id])
    assert result[cluster.id] == urls["press"][1]  # the newer of the two


@requires_postgres
def test_top_variant_urls_empty_for_no_ids(pg):
    from app.core.queries import get_top_variant_urls

    assert get_top_variant_urls(pg, []) == {}


@requires_postgres
def test_rss_feed_is_wellformed_and_links_to_top_source(pg):
    import xml.etree.ElementTree as ET

    from app.routers.feed import rss_feed

    now = datetime.now(timezone.utc)
    cluster, urls = _make_cluster_with_variants(
        pg,
        [("other", now - timedelta(hours=1)), ("official", now - timedelta(hours=2))],
    )

    response = rss_feed(db=pg)
    assert response.media_type == "application/rss+xml"

    root = ET.fromstring(response.body)  # raises if malformed
    links = [item.findtext("link") for item in root.iter("item")]
    assert urls["official"][0] in links
