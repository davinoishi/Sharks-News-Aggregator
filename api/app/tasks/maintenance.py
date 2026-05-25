"""
Maintenance tasks for cleanup and housekeeping.
"""
import re
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


@celery.task(name="app.tasks.maintenance.cleanup_bogus_entities")
def cleanup_bogus_entities():
    """
    Remove entities whose names contain no letters (e.g. "115", "4").
    These are created when the roster sync captures non-name values
    from CapWages HTML. Also removes their cluster associations and
    cleans up entities_agg on affected clusters.
    """
    from app.models import Entity, ClusterEntity, Cluster

    db = SessionLocal()
    try:
        bogus = db.query(Entity).filter(
            ~Entity.name.op('~')(r'[a-zA-Z]')
        ).all()

        if not bogus:
            print("No bogus entities found.")
            return {"status": "success", "deleted": 0}

        bogus_ids = {e.id for e in bogus}
        print(f"Found {len(bogus_ids)} bogus entities: {[e.name for e in bogus]}")

        db.query(ClusterEntity).filter(
            ClusterEntity.entity_id.in_(bogus_ids)
        ).delete(synchronize_session='fetch')

        clusters = db.query(Cluster).filter(
            Cluster.entities_agg.overlap(list(bogus_ids))
        ).all()
        for cluster in clusters:
            cluster.entities_agg = [
                eid for eid in (cluster.entities_agg or [])
                if eid not in bogus_ids
            ]

        for entity in bogus:
            db.delete(entity)

        db.commit()
        print(f"Deleted {len(bogus_ids)} bogus entities and cleaned up associations.")

        return {"status": "success", "deleted": len(bogus_ids)}

    finally:
        db.close()
