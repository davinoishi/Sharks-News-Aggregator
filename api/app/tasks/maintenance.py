"""
Maintenance tasks for cleanup and housekeeping.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery
from app.core.database import SessionLocal


@celery.task(name="app.tasks.maintenance.cleanup_expired_cache")
def cleanup_expired_cache():
    """
    Clean up expired feed cache entries.
    Runs hourly via Celery Beat.
    """
    db = SessionLocal()
    try:
        # TODO: Delete expired cache entries
        # db.query(FeedCache).filter(FeedCache.expires_at < datetime.utcnow()).delete()
        # db.commit()

        return {"status": "pending_implementation"}

    finally:
        db.close()


@celery.task(name="app.tasks.maintenance.purge_old_items")
def purge_old_items():
    """
    Delete clusters and raw_items older than 30 days.
    CASCADE foreign keys handle cleanup of:
      - cluster_variants, cluster_tags, cluster_entities (from clusters)
      - story_variants, cluster_variants (from raw_items)
      - submissions get NULLed references
    Runs daily via Celery Beat.
    """
    from app.models import Cluster, RawItem

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)

        # Delete old clusters (last_seen_at > 30 days ago)
        old_clusters = db.query(Cluster).filter(Cluster.last_seen_at < cutoff).all()
        clusters_deleted = len(old_clusters)
        for cluster in old_clusters:
            db.delete(cluster)
        db.commit()

        # Delete old raw_items (created_at > 30 days ago)
        # Cascades to story_variants and their cluster_variants
        old_items = db.query(RawItem).filter(RawItem.created_at < cutoff).all()
        items_deleted = len(old_items)
        for item in old_items:
            db.delete(item)
        db.commit()

        print(f"Purge complete: {clusters_deleted} clusters, {items_deleted} raw_items deleted (cutoff: {cutoff})")

        return {
            "status": "success",
            "clusters_deleted": clusters_deleted,
            "raw_items_deleted": items_deleted,
            "cutoff": cutoff.isoformat(),
        }

    finally:
        db.close()
