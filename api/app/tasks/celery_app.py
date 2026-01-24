from celery import Celery
from app.core.config import settings

celery = Celery(
    "sharks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.ingest", "app.tasks.enrich", "app.tasks.submissions", "app.tasks.sync_roster", "app.tasks.maintenance"]
)

# Celery configuration
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3000,  # 50 minutes soft limit
)

# Beat schedule for periodic tasks
celery.conf.beat_schedule = {
    "ingest-all-sources": {
        "task": "app.tasks.ingest.ingest_all_sources",
        "schedule": settings.ingest_interval_minutes * 60.0,  # Convert to seconds
    },
    "sync-sharks-roster": {
        "task": "app.tasks.sync_roster.sync_sharks_roster",
        "schedule": 86400.0,  # Once per day (24 hours)
    },
    "cleanup-old-feed-cache": {
        "task": "app.tasks.maintenance.cleanup_expired_cache",
        "schedule": 3600.0,  # Every hour
    },
    "purge-old-items": {
        "task": "app.tasks.maintenance.purge_old_items",
        "schedule": 86400.0,  # Once per day (24 hours)
    },
}
