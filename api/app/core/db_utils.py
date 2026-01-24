"""
Database utility functions for common operations.
"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.models import (
    Source, SourceStatus, Tag, Entity, Cluster, ClusterStatus,
    StoryVariant, ClusterVariant, ClusterTag, ClusterEntity
)


def get_or_create_tag(db: Session, name: str, slug: str, color: Optional[str] = None) -> Tag:
    """
    Get existing tag or create new one.

    Args:
        db: Database session
        name: Tag display name
        slug: Tag slug
        color: Optional hex color

    Returns:
        Tag object
    """
    tag = db.query(Tag).filter(Tag.slug == slug).first()
    if not tag:
        tag = Tag(name=name, slug=slug, display_color=color)
        db.add(tag)
        db.flush()
    return tag


def get_or_create_entity(
    db: Session,
    name: str,
    entity_type: str,
    extra_metadata: Optional[dict] = None
) -> Entity:
    """
    Get existing entity or create/update one.

    If the entity already exists, its metadata is updated with the new values.

    Args:
        db: Database session
        name: Entity name
        entity_type: 'player', 'coach', 'team', 'staff'
        extra_metadata: Optional metadata dict

    Returns:
        Entity object
    """
    slug = Entity.make_slug(name)
    entity = db.query(Entity).filter(Entity.slug == slug).first()

    if not entity:
        entity = Entity(
            name=name,
            slug=slug,
            entity_type=entity_type,
            extra_metadata=extra_metadata or {}
        )
        db.add(entity)
        db.flush()
    elif extra_metadata:
        entity.extra_metadata = extra_metadata
        db.flush()

    return entity


def get_active_sources(db: Session) -> List[Source]:
    """
    Get all approved sources for ingestion.

    Returns:
        List of approved Source objects ordered by priority
    """
    return db.query(Source).filter(
        Source.status == SourceStatus.APPROVED
    ).order_by(Source.priority.asc()).all()


def get_tag_by_slug(db: Session, slug: str) -> Optional[Tag]:
    """Get tag by slug."""
    return db.query(Tag).filter(Tag.slug == slug).first()


def get_entity_by_slug(db: Session, slug: str) -> Optional[Entity]:
    """Get entity by slug."""
    return db.query(Entity).filter(Entity.slug == slug).first()


def add_tags_to_cluster(db: Session, cluster: Cluster, tag_names: List[str]):
    """
    Add tags to a cluster (idempotent).

    Args:
        db: Database session
        cluster: Cluster object
        tag_names: List of tag names to add
    """
    for tag_name in tag_names:
        # Find tag (case-insensitive)
        tag = db.query(Tag).filter(
            func.lower(Tag.name) == tag_name.lower()
        ).first()

        if tag:
            # Check if already associated
            existing = db.query(ClusterTag).filter(
                and_(
                    ClusterTag.cluster_id == cluster.id,
                    ClusterTag.tag_id == tag.id
                )
            ).first()

            if not existing:
                cluster_tag = ClusterTag(cluster_id=cluster.id, tag_id=tag.id)
                db.add(cluster_tag)


def add_entities_to_cluster(db: Session, cluster: Cluster, entity_ids: List[int]):
    """
    Add entities to a cluster (idempotent).

    Args:
        db: Database session
        cluster: Cluster object
        entity_ids: List of entity IDs to add
    """
    for entity_id in entity_ids:
        # Check if already associated
        existing = db.query(ClusterEntity).filter(
            and_(
                ClusterEntity.cluster_id == cluster.id,
                ClusterEntity.entity_id == entity_id
            )
        ).first()

        if not existing:
            cluster_entity = ClusterEntity(cluster_id=cluster.id, entity_id=entity_id)
            db.add(cluster_entity)


def get_candidate_clusters(
    db: Session,
    event_type: str,
    time_window: timedelta
) -> List[Cluster]:
    """
    Get candidate clusters for matching within time window.

    Args:
        db: Database session
        event_type: Event type to match
        time_window: Time window to look back

    Returns:
        List of active clusters within time window
    """
    cutoff_time = datetime.utcnow() - time_window

    return db.query(Cluster).filter(
        and_(
            Cluster.status == ClusterStatus.ACTIVE,
            Cluster.last_seen_at >= cutoff_time
        )
    ).all()


def attach_variant_to_cluster(
    db: Session,
    cluster: Cluster,
    variant: StoryVariant,
    similarity_score: float
):
    """
    Attach a variant to a cluster.

    Args:
        db: Database session
        cluster: Cluster object
        variant: StoryVariant object
        similarity_score: Computed similarity score
    """
    # Check if already attached
    existing = db.query(ClusterVariant).filter(
        and_(
            ClusterVariant.cluster_id == cluster.id,
            ClusterVariant.variant_id == variant.id
        )
    ).first()

    if not existing:
        cluster_variant = ClusterVariant(
            cluster_id=cluster.id,
            variant_id=variant.id,
            similarity_score=similarity_score
        )
        db.add(cluster_variant)

        # Update cluster timestamps
        if variant.published_at:
            if not cluster.first_seen_at or variant.published_at < cluster.first_seen_at:
                cluster.first_seen_at = variant.published_at
            if not cluster.last_seen_at or variant.published_at > cluster.last_seen_at:
                cluster.last_seen_at = variant.published_at

        # Update source count
        cluster.update_source_count(db)


def find_variant_by_url(db: Session, url: str) -> Optional[StoryVariant]:
    """
    Find existing variant by URL.

    Args:
        db: Database session
        url: Canonical URL

    Returns:
        StoryVariant if found, None otherwise
    """
    return db.query(StoryVariant).filter(StoryVariant.url == url).first()


def check_submission_rate_limit(
    db: Session,
    ip_address: str,
    limit: int = 10,
    window_hours: int = 1
) -> bool:
    """
    Check if IP address has exceeded submission rate limit.

    Args:
        db: Database session
        ip_address: IP address to check
        limit: Max submissions per window
        window_hours: Time window in hours

    Returns:
        True if rate limited, False if OK to proceed
    """
    from app.models.submission import Submission

    cutoff_time = datetime.utcnow() - timedelta(hours=window_hours)

    count = db.query(func.count(Submission.id)).filter(
        and_(
            Submission.submitter_ip == ip_address,
            Submission.created_at >= cutoff_time
        )
    ).scalar()

    return count >= limit
