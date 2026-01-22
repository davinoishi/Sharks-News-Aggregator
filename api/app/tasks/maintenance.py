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


@celery.task(name="app.tasks.maintenance.archive_old_clusters")
def archive_old_clusters():
    """
    Archive clusters that haven't been updated in 30+ days.
    Optional task, not in beat schedule by default.
    """
    db = SessionLocal()
    try:
        # TODO: Mark old clusters as archived
        # cutoff_date = datetime.utcnow() - timedelta(days=30)
        # db.query(Cluster).filter(
        #     Cluster.last_seen_at < cutoff_date,
        #     Cluster.status == 'active'
        # ).update({'status': 'archived'})
        # db.commit()

        return {"status": "pending_implementation"}

    finally:
        db.close()
