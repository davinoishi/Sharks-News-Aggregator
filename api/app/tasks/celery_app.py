from celery import Celery

from app.core.config import settings
from app.core.logging_config import configure_logging

# Apply our timestamped, LOG_LEVEL-aware logging format process-wide before
# Celery starts. ``worker_hijack_root_logger=False`` (below) keeps Celery from
# overwriting it (brief 09, C4).
configure_logging()

celery = Celery(
    "sharks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.ingest", "app.tasks.enrich", "app.tasks.submissions", "app.tasks.sync_roster", "app.tasks.maintenance", "app.tasks.bluesky"]
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
    # Keep our configure_logging() format (timestamps + LOG_LEVEL) instead of
    # letting Celery reconfigure the root logger (brief 09, C4).
    worker_hijack_root_logger=False,
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
    "purge-old-items": {
        "task": "app.tasks.maintenance.purge_old_items",
        "schedule": 86400.0,  # Once per day (24 hours)
    },
    "monitor-pipeline-health": {
        "task": "app.tasks.maintenance.monitor_pipeline_health",
        "schedule": 1800.0,  # Every 30 minutes (brief 09, O3)
    },
    "bluesky-post-new-clusters": {
        "task": "app.tasks.bluesky.post_new_clusters",
        "schedule": settings.bluesky_post_interval_minutes * 60.0,  # Default 15 minutes
    },
    "bluesky-retry-failed-posts": {
        "task": "app.tasks.bluesky.retry_failed_posts",
        "schedule": 3600.0,  # Every hour
    },
}
