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

        result = list_entities(query="", limit=15, order_by="name", since=None, db=db)
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


@requires_postgres
def test_rss_channel_metadata_follows_public_site_url(pg, monkeypatch):
    """Channel <link> and atom:self must derive from the configured site URL.

    SEO-11: production ran for weeks publishing a channel origin that 404ed,
    because the deployed PUBLIC_SITE_URL had drifted. A test cannot catch a
    wrong *deployed* value — the fix for that is pinning it in
    docker-compose.pi.yml — but it can stop a refactor from hardcoding the
    origin or dropping the setting, which would make the value unfixable
    without a code change.
    """
    import xml.etree.ElementTree as ET

    from app.core.config import settings
    from app.routers.feed import rss_feed

    monkeypatch.setattr(settings, "public_site_url", "https://example.test/")

    now = datetime.now(timezone.utc)
    _make_cluster_with_variants(pg, [("official", now - timedelta(hours=1))])

    root = ET.fromstring(rss_feed(db=pg).body)
    channel = root.find("channel")

    # Trailing slash is stripped, so the two never disagree by a slash.
    assert channel.findtext("link") == "https://example.test"

    atom_self = channel.find("{http://www.w3.org/2005/Atom}link")
    assert atom_self.get("href") == "https://example.test/rss"
    assert atom_self.get("rel") == "self"


# ---------------------------------------------------------------------------
# Brief 12 (SEO-2 / SEO-3): prominence ordering and the public source list.


def _make_entity_cluster(db, headline, entity, *, last_seen_at, active=True):
    """Attach ``entity`` to a new cluster. Returns the cluster."""
    from app.models import Cluster, ClusterEntity, ClusterStatus

    cluster = Cluster(
        headline=headline,
        first_seen_at=last_seen_at,
        last_seen_at=last_seen_at,
        status=ClusterStatus.ACTIVE if active else ClusterStatus.ARCHIVED,
        source_count=1,
    )
    db.add(cluster)
    db.flush()
    db.add(ClusterEntity(cluster_id=cluster.id, entity_id=entity.id))
    db.flush()
    return cluster


@requires_postgres
def test_entities_cluster_count_ordering_ranks_by_coverage(pg):
    """The chip strip must lead with who is actually in the news.

    Alphabetical ordering (the endpoint default) would pin whoever sorts first
    to the top permanently — on the live site that was Adam Gaudette, who had
    no current coverage at all.
    """
    now = datetime.now(timezone.utc)

    # Deliberately named so alphabetical and by-coverage orders disagree: if the
    # ranking silently fell back to name order, this test would still see
    # "Aaron" first and pass. It must not be able to.
    aaron = Entity(name="Aaron Quiet", slug=_uniq("aaron"), entity_type="player")
    zack = Entity(name="Zack Everywhere", slug=_uniq("zack"), entity_type="player")
    pg.add_all([aaron, zack])
    pg.flush()

    for i in range(3):
        _make_entity_cluster(pg, f"Zack story {i}", zack, last_seen_at=now)
    _make_entity_cluster(pg, "Aaron story", aaron, last_seen_at=now)

    result = list_entities(
        query="", limit=15, order_by="cluster_count", since="24h", db=pg
    )
    names = [e["name"] for e in result["entities"]]

    assert names.index("Zack Everywhere") < names.index("Aaron Quiet")


@requires_postgres
def test_entities_cluster_count_respects_the_since_window(pg):
    """Chips are scoped to the window the feed is showing.

    If they weren't, a player who was everywhere last month would sit at the
    top of a 24-hour feed, and clicking the chip would return nothing.
    """
    now = datetime.now(timezone.utc)

    recent = Entity(name="Recent Player", slug=_uniq("recent"), entity_type="player")
    stale = Entity(name="Stale Player", slug=_uniq("stale"), entity_type="player")
    pg.add_all([recent, stale])
    pg.flush()

    _make_entity_cluster(pg, "Fresh", recent, last_seen_at=now - timedelta(hours=2))
    for i in range(5):
        _make_entity_cluster(
            pg, f"Old {i}", stale, last_seen_at=now - timedelta(days=20)
        )

    result = list_entities(
        query="", limit=15, order_by="cluster_count", since="24h", db=pg
    )
    names = [e["name"] for e in result["entities"]]

    assert "Recent Player" in names
    # Five clusters would dominate any unscoped count.
    assert "Stale Player" not in names


@requires_postgres
def test_entities_cluster_count_ignores_inactive_clusters(pg):
    """Must match build_feed_query's status filter.

    If the two drift, a chip offers a filter whose results are empty, which
    reads to a visitor as a broken feed.
    """
    now = datetime.now(timezone.utc)

    ghost = Entity(name="Ghost Player", slug=_uniq("ghost"), entity_type="player")
    pg.add(ghost)
    pg.flush()
    _make_entity_cluster(pg, "Archived", ghost, last_seen_at=now, active=False)

    result = list_entities(
        query="", limit=15, order_by="cluster_count", since="24h", db=pg
    )
    assert "Ghost Player" not in [e["name"] for e in result["entities"]]


@requires_postgres
def test_public_sources_publishes_only_whitelisted_fields(pg):
    """The public shape must not grow fields by accident.

    ``/admin/sources`` exposes feed URLs, error counts and status; this
    endpoint is a different, deliberately narrow view. A future column on the
    model must not appear here just because it was added.
    """
    from app.core.constants import USER_SUBMISSION_SOURCE_URL
    from app.models import Source, SourceStatus
    from app.routers.feed import list_public_sources

    pg.add(
        Source(
            name="Visible Outlet",
            category="press",
            ingest_method="rss",
            base_url="https://visible.example.com",
            feed_url="https://visible.example.com/secret-feed.xml",
            status=SourceStatus.APPROVED,
            fetch_error_count=7,
        )
    )
    pg.flush()

    result = list_public_sources(db=pg)
    published = [s for s in result["sources"] if s["name"] == "Visible Outlet"]
    assert len(published) == 1
    assert set(published[0].keys()) == {"name", "base_url", "category"}

    # Nothing operational leaks, whatever the serialiser does.
    serialised = str(result)
    assert "secret-feed" not in serialised
    assert USER_SUBMISSION_SOURCE_URL not in serialised


@requires_postgres
def test_public_sources_excludes_submissions_and_unapproved(pg):
    """The submission bucket is an internal sink, not an outlet to link to."""
    from app.core.constants import USER_SUBMISSION_SOURCE_URL
    from app.models import Source, SourceStatus
    from app.routers.feed import list_public_sources

    pg.add_all([
        Source(
            name="User Submissions",
            category="other",
            ingest_method="rss",
            base_url=USER_SUBMISSION_SOURCE_URL,
            status=SourceStatus.APPROVED,
        ),
        Source(
            name="Rejected Outlet",
            category="other",
            ingest_method="rss",
            base_url="https://rejected.example.com",
            status=SourceStatus.REJECTED,
        ),
        Source(
            name="Unsupported Outlet",
            category="other",
            ingest_method="html",
            base_url="https://unsupported.example.com",
            status=SourceStatus.UNSUPPORTED,
        ),
    ])
    pg.flush()

    names = [s["name"] for s in list_public_sources(db=pg)["sources"]]
    assert "User Submissions" not in names
    assert "Rejected Outlet" not in names
    assert "Unsupported Outlet" not in names


# --- brief 16 EV-1: the parsed verdict is stored, not re-derived --------------

def test_log_validation_stores_the_parsed_verdict():
    """EV-1: analysis should be ordinary SQL, not a prefix match on JSON."""
    from app.utils import parse_llm_approved

    assert parse_llm_approved('{"relevant": true, "confidence": "HIGH"}') is True
    assert parse_llm_approved('{"relevant": false}') is False
    # Truncated at 100 chars — the shape 577 of 581 production rows are in.
    truncated = '{"relevant": true, "reason": "Article covers the San Jose Sharks roster and their pro'
    assert parse_llm_approved(truncated) is True
    # Nothing recoverable.
    assert parse_llm_approved("") is False


def test_validation_log_accepts_an_untruncated_response(pg_db):
    """The column is Text now; a full OpenRouter payload must round-trip."""
    from app.models import IngestMethod, RawItem, Source, SourceCategory
    from app.models.validation_log import (
        ValidationLog,
        ValidationMethod,
        ValidationResult,
    )

    source = Source(
        name="EV1 Src",
        category=SourceCategory.PRESS,
        ingest_method=IngestMethod.RSS,
        base_url="https://ev1.example.com",
    )
    pg_db.add(source)
    pg_db.flush()
    raw = RawItem(
        source_id=source.id,
        original_url="https://ev1.example.com/a",
        canonical_url="https://ev1.example.com/a",
        raw_title="A",
    )
    pg_db.add(raw)
    pg_db.flush()

    long_response = '{"relevant": true, "reason": "' + ("x" * 500) + '"}'
    log = ValidationLog(
        raw_item_id=raw.id,
        method=ValidationMethod.LLM,
        result=ValidationResult.APPROVED,
        llm_response=long_response,
        llm_relevant=True,
    )
    pg_db.add(log)
    pg_db.flush()
    pg_db.refresh(log)
    assert log.llm_response == long_response
    assert len(log.llm_response) > 100
    assert log.llm_relevant is True
