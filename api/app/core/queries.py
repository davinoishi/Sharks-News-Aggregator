"""
Query builder functions for feed and cluster endpoints.
"""
import base64
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    Cluster,
    ClusterEntity,
    ClusterStatus,
    ClusterTag,
    ClusterVariant,
    Entity,
    Source,
    StoryVariant,
    Tag,
)

# Decoded keyset cursor: (last_seen_at, cluster_id).
CursorKey = Tuple[datetime, int]


def encode_cursor(last_seen_at: datetime, cluster_id: int) -> str:
    """Opaque base64 cursor for keyset pagination on (last_seen_at, id)."""
    raw = f"{last_seen_at.isoformat()}:{cluster_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: Optional[str]) -> Optional[CursorKey]:
    """Decode a cursor to ``(last_seen_at, id)``.

    Returns ``None`` for an absent cursor or anything unparseable — including the
    old numeric offset cursors clients may still have cached (treated as "start
    from the top" rather than erroring).
    """
    if not cursor or cursor.isdigit():
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts_str, id_str = raw.rsplit(":", 1)
        return datetime.fromisoformat(ts_str), int(id_str)
    except (ValueError, TypeError):
        return None


def build_feed_query(
    db: Session,
    tag_slugs: Optional[List[str]] = None,
    entity_slugs: Optional[List[str]] = None,
    since: Optional[datetime] = None,
    limit: int = 50,
    cursor: Optional[CursorKey] = None,
) -> Tuple[List[Cluster], bool]:
    """
    Build and execute the feed query with filters and keyset pagination.

    Semantics: a cluster matches if it has ANY of the requested tags AND ANY of
    the requested entities. Filters use EXISTS subqueries so a cluster matching
    several requested tags is still returned exactly once (fixes the old
    join-based duplication, C1). If a requested slug list resolves to zero known
    tags/entities, the feed is empty rather than silently unfiltered.

    Tags+entities are eager-loaded (selectinload) so formatting the page does no
    per-cluster queries (P1). We fetch ``limit + 1`` rows to derive ``has_more``
    instead of a full ``count()`` (P2), and paginate by keyset on
    ``(last_seen_at, id)`` so shifting ``last_seen_at`` values can't cause
    skips/dupes across pages (P3).

    Returns:
        Tuple of (clusters, has_more).
    """
    query = db.query(Cluster).filter(Cluster.status == ClusterStatus.ACTIVE)

    if since:
        query = query.filter(Cluster.last_seen_at >= since)

    # Tag filter (ANY of the requested tags) via EXISTS — no row duplication.
    if tag_slugs:
        tag_ids = [t[0] for t in db.query(Tag.id).filter(Tag.slug.in_(tag_slugs)).all()]
        if not tag_ids:
            return [], False
        query = query.filter(
            db.query(ClusterTag.cluster_id)
            .filter(
                ClusterTag.cluster_id == Cluster.id,
                ClusterTag.tag_id.in_(tag_ids),
            )
            .exists()
        )

    # Entity filter (ANY of the requested entities) via EXISTS.
    if entity_slugs:
        entity_ids = [e[0] for e in db.query(Entity.id).filter(Entity.slug.in_(entity_slugs)).all()]
        if not entity_ids:
            return [], False
        query = query.filter(
            db.query(ClusterEntity.cluster_id)
            .filter(
                ClusterEntity.cluster_id == Cluster.id,
                ClusterEntity.entity_id.in_(entity_ids),
            )
            .exists()
        )

    # Keyset pagination: rows strictly after the cursor in (last_seen_at, id) desc.
    if cursor is not None:
        cursor_ts, cursor_id = cursor
        query = query.filter(
            or_(
                Cluster.last_seen_at < cursor_ts,
                and_(Cluster.last_seen_at == cursor_ts, Cluster.id < cursor_id),
            )
        )

    query = query.options(
        selectinload(Cluster.cluster_tags).selectinload(ClusterTag.tag),
        selectinload(Cluster.cluster_entities).selectinload(ClusterEntity.entity),
    ).order_by(desc(Cluster.last_seen_at), desc(Cluster.id))

    rows = query.limit(limit + 1).all()
    has_more = len(rows) > limit
    return rows[:limit], has_more


def get_cluster_with_details(db: Session, cluster_id: int) -> Optional[Cluster]:
    """
    Get cluster with all related data eagerly loaded.

    Args:
        db: Database session
        cluster_id: Cluster ID

    Returns:
        Cluster object with relationships loaded, or None
    """
    cluster = db.query(Cluster).filter(
        Cluster.id == cluster_id
    ).options(
        joinedload(Cluster.cluster_tags).joinedload(ClusterTag.tag),
        joinedload(Cluster.cluster_entities).joinedload(ClusterEntity.entity),
        joinedload(Cluster.cluster_variants).joinedload(ClusterVariant.variant).joinedload(StoryVariant.source)
    ).first()

    return cluster


def get_cluster_variants_sorted(db: Session, cluster_id: int) -> List[StoryVariant]:
    """
    Get all variants for a cluster, sorted by source category and recency.

    Sorting order:
    1. Official sources first
    2. Then press sources
    3. Then other sources
    4. Within each category, most recent first

    Args:
        db: Database session
        cluster_id: Cluster ID

    Returns:
        List of StoryVariant objects sorted appropriately
    """
    variants = db.query(StoryVariant).join(
        ClusterVariant
    ).join(
        Source
    ).filter(
        ClusterVariant.cluster_id == cluster_id
    ).order_by(
        desc(Source.category),  # Enum ordering: official > press > other
        desc(StoryVariant.published_at)
    ).all()

    return variants


def format_cluster_for_feed(db: Session, cluster: Cluster) -> dict:
    """
    Format a cluster for feed API response.

    Args:
        db: Database session
        cluster: Cluster object

    Returns:
        Dictionary formatted for API response
    """
    # Get tags
    tags = [
        {
            "id": ct.tag.id,
            "name": ct.tag.name,
            "slug": ct.tag.slug,
            "color": ct.tag.display_color,
        }
        for ct in cluster.cluster_tags
    ]

    # Get entities
    entities = [
        {
            "id": ce.entity.id,
            "name": ce.entity.name,
            "slug": ce.entity.slug,
            "type": ce.entity.entity_type,
        }
        for ce in cluster.cluster_entities
    ]

    return {
        "id": cluster.id,
        "headline": cluster.headline,
        "event_type": cluster.event_type.value if hasattr(cluster.event_type, 'value') else cluster.event_type,
        "first_seen_at": cluster.first_seen_at.isoformat() if cluster.first_seen_at else None,
        "last_seen_at": cluster.last_seen_at.isoformat() if cluster.last_seen_at else None,
        "source_count": cluster.source_count,
        "click_count": cluster.click_count or 0,
        "tags": tags,
        "entities": entities,
    }


def format_cluster_detail(db: Session, cluster: Cluster) -> dict:
    """
    Format a cluster for detail API response with all variants.

    Args:
        db: Database session
        cluster: Cluster object

    Returns:
        Dictionary formatted for API response
    """
    # Get base cluster info
    result = format_cluster_for_feed(db, cluster)

    # Get sorted variants
    variants = get_cluster_variants_sorted(db, cluster.id)

    result["variants"] = [variant.to_dict() for variant in variants]

    return result


def search_entities_by_name(db: Session, query: str, limit: int = 10) -> List[Entity]:
    """
    Search entities by name (case-insensitive partial match).

    Args:
        db: Database session
        query: Search query
        limit: Max results

    Returns:
        List of matching entities
    """
    return db.query(Entity).filter(
        Entity.name.ilike(f"%{query}%")
    ).limit(limit).all()


def get_recent_clusters_count(db: Session, hours: int = 24) -> int:
    """
    Get count of clusters updated in the last N hours.

    Args:
        db: Database session
        hours: Time window in hours

    Returns:
        Count of recent clusters
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    return db.query(func.count(Cluster.id)).filter(
        and_(
            Cluster.status == ClusterStatus.ACTIVE,
            Cluster.last_seen_at >= cutoff
        )
    ).scalar()


def get_tag_distribution(db: Session) -> List[dict]:
    """
    Get distribution of tags across active clusters.

    Returns:
        List of dicts with tag info and cluster count
    """
    results = db.query(
        Tag.id,
        Tag.name,
        Tag.slug,
        func.count(ClusterTag.cluster_id).label('cluster_count')
    ).join(
        ClusterTag
    ).join(
        Cluster
    ).filter(
        Cluster.status == ClusterStatus.ACTIVE
    ).group_by(
        Tag.id, Tag.name, Tag.slug
    ).order_by(
        desc('cluster_count')
    ).all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "slug": r.slug,
            "cluster_count": r.cluster_count,
        }
        for r in results
    ]
