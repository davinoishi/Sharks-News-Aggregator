"""Feed query correctness + performance tests (brief 04: C1/P1/P2/P3).

These require PostgreSQL — the ``clusters`` table uses ARRAY columns that SQLite
cannot create — so the whole module is skipped unless DATABASE_URL points at
Postgres. CI runs them against a postgres service (see the feed-tests job).
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DB_URL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DB_URL.startswith("postgresql"),
    reason="feed query tests require PostgreSQL (clusters uses ARRAY columns)",
)

from app.core.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    Cluster, ClusterStatus, Tag, Entity, ClusterTag, ClusterEntity,
)
from app.core.queries import (  # noqa: E402
    build_feed_query, format_cluster_for_feed, encode_cursor, decode_cursor,
)


@pytest.fixture
def db():
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine)
    conn = engine.connect()
    trans = conn.begin()  # rolled back after each test → isolated, no leftovers
    session = sessionmaker(bind=conn)()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()
        engine.dispose()


_seq = 0


def _uniq(prefix: str) -> str:
    global _seq
    _seq += 1
    return f"{prefix}-{_seq}"


def _tag(db, name="tag"):
    t = Tag(name=_uniq(name), slug=_uniq(name))
    db.add(t)
    db.flush()
    return t


def _entity(db, name="ent"):
    e = Entity(name=_uniq(name), slug=_uniq(name), entity_type="player")
    db.add(e)
    db.flush()
    return e


def _cluster(db, headline, last_seen_at, tags=(), entities=()):
    c = Cluster(
        headline=headline,
        first_seen_at=last_seen_at,
        last_seen_at=last_seen_at,
        status=ClusterStatus.ACTIVE,
        source_count=1,
    )
    db.add(c)
    db.flush()
    for t in tags:
        db.add(ClusterTag(cluster_id=c.id, tag_id=t.id))
    for e in entities:
        db.add(ClusterEntity(cluster_id=c.id, entity_id=e.id))
    db.flush()
    return c


def test_duplicate_tag_cluster_appears_once(db):
    # C1: a cluster matching multiple requested tags must appear exactly once.
    t1, t2 = _tag(db, "a"), _tag(db, "b")
    c = _cluster(db, "two tags", datetime.now(timezone.utc), tags=[t1, t2])

    clusters, has_more = build_feed_query(db, tag_slugs=[t1.slug, t2.slug], limit=50)

    assert [x.id for x in clusters] == [c.id]
    assert has_more is False


def test_unknown_slug_returns_empty_not_unfiltered(db):
    _cluster(db, "visible", datetime.now(timezone.utc))  # would show if unfiltered

    clusters, has_more = build_feed_query(db, tag_slugs=["nope-not-a-tag"], limit=50)
    assert clusters == []
    assert has_more is False

    clusters, _ = build_feed_query(db, entity_slugs=["nope-not-an-entity"], limit=50)
    assert clusters == []


def test_keyset_pagination_walks_full_set_while_last_seen_shifts(db):
    base = datetime.now(timezone.utc)
    created = [_cluster(db, f"c{i}", base - timedelta(minutes=i)) for i in range(7)]
    all_ids = {c.id for c in created}

    seen: list[int] = []
    cursor = None
    bumped = False
    for _ in range(20):  # safety bound
        clusters, has_more = build_feed_query(db, limit=2, cursor=decode_cursor(cursor))
        seen.extend(c.id for c in clusters)

        # Mid-walk, push an already-seen cluster's last_seen_at to the top.
        # Keyset must not re-emit it (no dup) nor drop the unseen ones (no skip).
        if not bumped and len(seen) >= 2:
            c = db.get(Cluster, seen[0])
            c.last_seen_at = base + timedelta(minutes=5)
            db.flush()
            bumped = True

        if not has_more:
            break
        last = clusters[-1]
        cursor = encode_cursor(last.last_seen_at, last.id)

    assert len(seen) == len(set(seen)), "no duplicates across pages"
    assert set(seen) == all_ids, "every cluster seen exactly once"


def test_feed_page_query_count_is_bounded(db):
    # P1: formatting a page must not run per-cluster queries.
    ta, tb = _tag(db, "alpha"), _tag(db, "beta")
    ent = _entity(db, "player")
    base = datetime.now(timezone.utc)
    for i in range(6):
        _cluster(db, f"c{i}", base - timedelta(minutes=i), tags=[ta, tb], entities=[ent])
    db.flush()

    conn = db.connection()
    count = {"n": 0}

    def _on_exec(*args, **kwargs):
        count["n"] += 1

    event.listen(conn, "before_cursor_execute", _on_exec)
    try:
        clusters, _ = build_feed_query(db, limit=50)
        items = [format_cluster_for_feed(db, c) for c in clusters]
    finally:
        event.remove(conn, "before_cursor_execute", _on_exec)

    assert len(items) == 6
    # main query + selectinload(cluster_tags, tag) + selectinload(cluster_entities, entity)
    # ~= 5 statements, independent of the cluster count (would be ~13 with N+1).
    assert count["n"] <= 6, f"expected bounded query count, got {count['n']}"
