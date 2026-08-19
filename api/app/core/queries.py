"""
Query builder functions for feed and cluster endpoints.
"""
import base64
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.datetime_utils import utcnow
from app.enrichment.clustering import normalize_title_for_matching
from app.models import (
    Cluster,
    ClusterEntity,
    ClusterRelation,
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


_CATEGORY_RANK = {"official": 3, "press": 2, "other": 1}


def get_top_variant_urls(db: Session, cluster_ids: List[int]) -> dict:
    """Map each cluster id to its top-ranked variant URL.

    "Top" follows the same official→press→other ordering used elsewhere
    (:func:`get_cluster_variants_sorted`), breaking ties by most-recent
    ``published_at``. Runs a single batched query for the whole page (no
    per-cluster round-trips), so the feed router can expose ``top_url`` without
    the frontend fetching cluster detail before navigating (U3).

    Returns:
        ``{cluster_id: url}`` for clusters that have at least one variant.
    """
    if not cluster_ids:
        return {}

    rows = (
        db.query(
            ClusterVariant.cluster_id,
            StoryVariant.url,
            Source.category,
            StoryVariant.published_at,
        )
        .join(StoryVariant, ClusterVariant.variant_id == StoryVariant.id)
        .join(Source, StoryVariant.source_id == Source.id)
        .filter(ClusterVariant.cluster_id.in_(cluster_ids))
        .all()
    )

    # Pick the best variant per cluster in Python: higher category rank wins,
    # then the more recent published_at.
    best: dict = {}  # cluster_id -> (rank, published_at, url)
    for cluster_id, url, category, published_at in rows:
        category_value = category.value if hasattr(category, "value") else category
        rank = _CATEGORY_RANK.get(category_value, 0)
        key = (rank, published_at or datetime.min.replace(tzinfo=timezone.utc))
        current = best.get(cluster_id)
        if current is None or key > current[0]:
            best[cluster_id] = (key, url)

    return {cluster_id: value[1] for cluster_id, value in best.items()}


# How many sibling headlines a card previews. Enough to make a mis-merge
# obvious, few enough to keep the card a card (brief 15, SK-5).
PREVIEW_HEADLINE_LIMIT = 3


def get_variant_headline_previews(db: Session, cluster_ids: List[int]) -> dict:
    """Map each cluster id to a few of its variants' headlines.

    Every variant title currently lives behind the "View sources" control, so a
    mis-merged story is invisible to a reader who has no reason to expand that
    card — which is exactly how the RM-4 card cost a reader the pipeline story.
    Surfacing a couple of sibling headlines makes a bad merge self-evident
    without an extra request, and salvages the story even when the matcher is
    wrong.

    Excludes the cluster's own headline, and any variant that is only the same
    headline wearing a publication suffix ("... - Yardbarker") — echoing the
    headline back at the reader is noise, and worse, it makes a card look like
    it corroborates itself.

    Ordered the same way the expanded list is (official→press→other, then
    recency) so the preview is a prefix of what expanding reveals, not a
    different set.

    Returns ``{cluster_id: [title, ...]}``, omitting clusters with nothing left
    to show.
    """
    if not cluster_ids:
        return {}

    rows = (
        db.query(
            ClusterVariant.cluster_id,
            StoryVariant.title,
            Source.category,
            StoryVariant.published_at,
        )
        .join(StoryVariant, ClusterVariant.variant_id == StoryVariant.id)
        .join(Source, StoryVariant.source_id == Source.id)
        .filter(ClusterVariant.cluster_id.in_(cluster_ids))
        .all()
    )

    headlines = dict(
        db.query(Cluster.id, Cluster.headline)
        .filter(Cluster.id.in_(cluster_ids))
        .all()
    )

    grouped: dict = {}
    for cluster_id, title, category, published_at in rows:
        if not title:
            continue
        category_value = category.value if hasattr(category, "value") else category
        rank = _CATEGORY_RANK.get(category_value, 0)
        sort_key = (rank, published_at or datetime.min.replace(tzinfo=timezone.utc))
        grouped.setdefault(cluster_id, []).append((sort_key, title))

    previews: dict = {}
    for cluster_id, entries in grouped.items():
        entries.sort(key=lambda e: e[0], reverse=True)
        # Compare on the normalized form so a publication suffix does not
        # smuggle the headline back in as a distinct string.
        headline_key = normalize_title_for_matching(headlines.get(cluster_id) or "")
        seen = {headline_key} if headline_key else set()
        titles = []
        for _, title in entries:
            key = normalize_title_for_matching(title)
            if not key or key in seen:
                continue
            seen.add(key)
            titles.append(title.strip())
        if titles:
            previews[cluster_id] = titles[:PREVIEW_HEADLINE_LIMIT]
    return previews


# Related stories shown per card. Three is enough to rescue a split story and
# few enough that the card does not become a second feed (brief 15, SK-4).
RELATED_CLUSTER_LIMIT = 3


def get_related_clusters(db: Session, cluster_ids: List[int]) -> dict:
    """Map each cluster id to the clusters the matcher nearly merged it with.

    Briefs 14 and 15 split more on purpose. This is what stops that costing the
    reader anything: a split card offers the sibling story instead of being a
    dead end.

    Relations are stored once per unordered pair (``cluster_a_id`` is always the
    smaller id), so a lookup has to match on either column and normalise the
    direction on the way out.

    Each related entry carries the top source URL, because there is no
    per-cluster page on the site to link to — the useful destination is the
    story itself.

    Returns ``{cluster_id: [{"id", "headline", "url"}, ...]}``.
    """
    if not cluster_ids:
        return {}

    rows = (
        db.query(
            ClusterRelation.cluster_a_id,
            ClusterRelation.cluster_b_id,
            ClusterRelation.score,
        )
        .filter(
            or_(
                ClusterRelation.cluster_a_id.in_(cluster_ids),
                ClusterRelation.cluster_b_id.in_(cluster_ids),
            )
        )
        .order_by(ClusterRelation.score.desc().nullslast())
        .all()
    )
    if not rows:
        return {}

    requested = set(cluster_ids)
    pairs: dict = {}
    other_ids = set()
    for a_id, b_id, score in rows:
        for owner, other in ((a_id, b_id), (b_id, a_id)):
            if owner in requested:
                bucket = pairs.setdefault(owner, [])
                if len(bucket) < RELATED_CLUSTER_LIMIT:
                    bucket.append((other, score))
                    other_ids.add(other)

    if not other_ids:
        return {}

    # Only active clusters: a related pointer into a purged or archived cluster
    # is worse than no pointer.
    headlines = dict(
        db.query(Cluster.id, Cluster.headline)
        .filter(Cluster.id.in_(other_ids), Cluster.status == ClusterStatus.ACTIVE)
        .all()
    )
    urls = get_top_variant_urls(db, list(headlines.keys()))

    related: dict = {}
    for owner, entries in pairs.items():
        items = [
            {
                "id": other,
                "headline": headlines[other],
                "url": urls.get(other),
            }
            for other, _ in entries
            if other in headlines
        ]
        if items:
            related[owner] = items
    return related


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


def get_entities_by_prominence(
    db: Session,
    since: Optional[datetime] = None,
    limit: int = 20,
) -> List[Entity]:
    """Entities ranked by how many clusters currently mention them.

    Alphabetical order is useless for a "who's in the news" strip — it pins
    whoever sorts first to the top forever, regardless of whether anyone is
    writing about them. This ranks by cluster count within the same window the
    feed is showing.

    The cluster filters here MUST match ``build_feed_query``
    (``status == ACTIVE`` plus the ``since`` bound). If they drift, the chips
    offer filters that return nothing, which reads as a broken feed.

    Ties break alphabetically so the order is stable between renders — an
    unstable order would churn the server-rendered HTML on every revalidate.
    """
    counts = (
        db.query(Entity, func.count(ClusterEntity.cluster_id).label("n"))
        .join(ClusterEntity, ClusterEntity.entity_id == Entity.id)
        .join(Cluster, Cluster.id == ClusterEntity.cluster_id)
        .filter(Cluster.status == ClusterStatus.ACTIVE)
    )

    if since:
        counts = counts.filter(Cluster.last_seen_at >= since)

    rows = (
        counts.group_by(Entity.id)
        .order_by(desc("n"), Entity.name)
        .limit(limit)
        .all()
    )
    return [entity for entity, _ in rows]


def get_recent_clusters_count(db: Session, hours: int = 24) -> int:
    """
    Get count of clusters updated in the last N hours.

    Args:
        db: Database session
        hours: Time window in hours

    Returns:
        Count of recent clusters
    """
    cutoff = utcnow() - timedelta(hours=hours)

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
