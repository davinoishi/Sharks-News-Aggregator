"""Feed and cluster-detail endpoints (brief 07, Q3)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.queries import (
    build_feed_query,
    decode_cursor,
    encode_cursor,
    format_cluster_for_feed,
    get_cluster_variants_sorted,
)
from app.models import Cluster, ClusterEntity, ClusterStatus, ClusterTag, Entity, Tag
from app.schemas import ClusterDetailResponse, FeedResponse
from app.utils import parse_since_parameter

router = APIRouter()


@router.get("/feed", response_model=FeedResponse)
def get_feed(
    tags: Optional[str] = Query(None, description="Comma-separated tag slugs"),
    entities: Optional[str] = Query(None, description="Comma-separated entity slugs"),
    since: Optional[str] = Query(None, description="Time filter: 24h|7d|30d or ISO timestamp"),
    limit: int = Query(50, ge=1, le=100, description="Number of clusters to return"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    db: Session = Depends(get_db)
):
    """
    Get the main feed of clustered stories.

    Query Parameters:
    - tags: Filter by tags (e.g., "rumors-press,injury")
    - entities: Filter by entities (e.g., "macklin-celebrini,will-smith")
    - since: Time filter (24h, 7d, 30d, or ISO timestamp)
    - limit: Number of results (default 50, max 100)
    - cursor: Pagination cursor from previous response

    Returns:
    - List of clusters with headline, tags, source count, etc.
    """
    # Parse time filter
    since_datetime = parse_since_parameter(since)

    # Parse tag and entity filters
    tag_list = tags.split(',') if tags else None
    entity_list = entities.split(',') if entities else None

    # Keyset pagination. Old numeric cursors decode to None (start from the top).
    cursor_key = decode_cursor(cursor)

    clusters, has_more = build_feed_query(
        db=db,
        tag_slugs=tag_list,
        entity_slugs=entity_list,
        since=since_datetime,
        limit=limit,
        cursor=cursor_key,
    )

    # Tags/entities are eager-loaded, so this does no per-cluster queries.
    cluster_items = [format_cluster_for_feed(db, cluster) for cluster in clusters]

    next_cursor = None
    if has_more and clusters:
        last = clusters[-1]
        next_cursor = encode_cursor(last.last_seen_at, last.id)

    return {
        "clusters": cluster_items,
        "cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/cluster/{cluster_id}", response_model=ClusterDetailResponse)
def get_cluster(
    cluster_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific cluster.

    Returns:
    - Cluster metadata
    - All source links (variants) grouped by category
    - Tags and entities
    """
    # Load cluster
    cluster = db.query(Cluster).filter(
        Cluster.id == cluster_id,
        Cluster.status == ClusterStatus.ACTIVE
    ).first()

    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Load tags
    cluster_tags = db.query(Tag).join(ClusterTag).filter(
        ClusterTag.cluster_id == cluster_id
    ).all()

    tags = [{"id": tag.id, "name": tag.name, "slug": tag.slug} for tag in cluster_tags]

    # Load entities
    cluster_entities = db.query(Entity).join(ClusterEntity).filter(
        ClusterEntity.cluster_id == cluster_id
    ).all()

    entities = [
        {"id": entity.id, "name": entity.name, "slug": entity.slug, "type": entity.entity_type}
        for entity in cluster_entities
    ]

    # Load variants sorted by source category
    variants_sorted = get_cluster_variants_sorted(db, cluster_id)

    variants = [
        {
            "variant_id": v.id,
            "title": v.title or "Untitled",
            "url": v.url,
            "published_at": v.published_at,
            "content_type": v.event_type.value,
            "source_name": v.source.name if v.source else "Unknown",
            "source_category": v.source.category.value if v.source else "other"
        }
        for v in variants_sorted
    ]

    return {
        "cluster_id": cluster.id,
        "headline": cluster.headline or (variants[0]["title"] if variants else "No headline"),
        "event_type": cluster.event_type.value,
        "first_seen_at": cluster.first_seen_at,
        "last_seen_at": cluster.last_seen_at,
        "tags": tags,
        "entities": entities,
        "variants": variants
    }
