"""
Query builder functions for feed and cluster endpoints.
"""
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func, desc

from app.models import (
    Cluster, ClusterStatus, StoryVariant, ClusterVariant,
    ClusterTag, ClusterEntity, Tag, Entity, Source
)


def build_feed_query(
    db: Session,
    tag_slugs: Optional[List[str]] = None,
    entity_slugs: Optional[List[str]] = None,
    since: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[Cluster], int]:
    """
    Build and execute feed query with filters.

    Args:
        db: Database session
        tag_slugs: List of tag slugs to filter by
        entity_slugs: List of entity slugs to filter by
        since: Filter clusters updated since this time
        limit: Max results to return
        offset: Offset for pagination

    Returns:
        Tuple of (clusters, total_count)
    """
    # Base query
    query = db.query(Cluster).filter(Cluster.status == ClusterStatus.ACTIVE)

    # Apply time filter
    if since:
        query = query.filter(Cluster.last_seen_at >= since)

    # Apply tag filter
    if tag_slugs:
        tag_ids = db.query(Tag.id).filter(Tag.slug.in_(tag_slugs)).all()
        tag_ids = [t[0] for t in tag_ids]

        if tag_ids:
            query = query.join(ClusterTag).filter(ClusterTag.tag_id.in_(tag_ids))

    # Apply entity filter
    if entity_slugs:
        entity_ids = db.query(Entity.id).filter(Entity.slug.in_(entity_slugs)).all()
        entity_ids = [e[0] for e in entity_ids]

        if entity_ids:
            query = query.join(ClusterEntity).filter(ClusterEntity.entity_id.in_(entity_ids))

    # Get total count before pagination
    total_count = query.count()

    # Order by last_seen_at descending (most recent first)
    query = query.order_by(desc(Cluster.last_seen_at))

    # Apply pagination
    query = query.limit(limit).offset(offset)

    # Execute and return
    clusters = query.all()

    return clusters, total_count


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
