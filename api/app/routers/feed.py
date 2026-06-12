"""Feed and cluster-detail endpoints (brief 07, Q3)."""
from email.utils import format_datetime
from typing import Optional
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.queries import (
    build_feed_query,
    decode_cursor,
    encode_cursor,
    format_cluster_for_feed,
    get_cluster_variants_sorted,
    get_top_variant_urls,
    search_entities_by_name,
)
from app.models import Cluster, ClusterEntity, ClusterStatus, ClusterTag, Entity, Tag
from app.schemas import ClusterDetailResponse, EntitiesResponse, FeedResponse
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

    # One batched query for the top source URL of every cluster on the page, so
    # the frontend can make headlines real links without fetching detail (U3).
    top_urls = get_top_variant_urls(db, [c.id for c in clusters])
    for item in cluster_items:
        item["top_url"] = top_urls.get(item["id"])

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


@router.get("/entities", response_model=EntitiesResponse)
def list_entities(
    query: str = Query("", description="Case-insensitive name search"),
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Public entity search for the player/entity filter picker (U2).

    Empty query returns the first ``limit`` entities alphabetically so the
    picker can show suggestions before the user types.
    """
    query = query.strip()
    if query:
        results = search_entities_by_name(db, query, limit=limit)
    else:
        results = db.query(Entity).order_by(Entity.name).limit(limit).all()

    return {
        "entities": [
            {"id": e.id, "name": e.name, "slug": e.slug, "type": e.entity_type}
            for e in results
        ]
    }


@router.get("/rss")
def rss_feed(db: Session = Depends(get_db)):
    """Published RSS 2.0 feed of the latest clusters (U5).

    Each item links to the cluster's top-ranked source; ``pubDate`` is
    ``last_seen_at`` and ``category`` is the event type.
    """
    clusters = (
        db.query(Cluster)
        .filter(Cluster.status == ClusterStatus.ACTIVE)
        .order_by(desc(Cluster.last_seen_at), desc(Cluster.id))
        .limit(50)
        .all()
    )

    top_urls = get_top_variant_urls(db, [c.id for c in clusters])
    site_url = settings.public_site_url.rstrip("/")
    self_url = f"{site_url}/rss"

    items = []
    for c in clusters:
        link = top_urls.get(c.id) or site_url
        event_type = c.event_type.value if hasattr(c.event_type, "value") else c.event_type
        pub_date = format_datetime(c.last_seen_at) if c.last_seen_at else ""
        items.append(
            "    <item>\n"
            f"      <title>{escape(c.headline or 'Untitled')}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid isPermaLink=\"false\">sharks-cluster-{c.id}</guid>\n"
            f"      <category>{escape(event_type)}</category>\n"
            f"      <pubDate>{escape(pub_date)}</pubDate>\n"
            "    </item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        "    <title>Sharks News Aggregator</title>\n"
        f"    <link>{escape(site_url)}</link>\n"
        "    <description>San Jose Sharks news and rumors, aggregated into one feed.</description>\n"
        "    <language>en-us</language>\n"
        f'    <atom:link href="{escape(self_url)}" rel="self" type="application/rss+xml" />\n'
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )

    return Response(
        content=xml,
        media_type="application/rss+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )
