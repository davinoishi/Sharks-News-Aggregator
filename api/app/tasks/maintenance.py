"""
Maintenance tasks for cleanup and housekeeping.
"""
import logging
from datetime import timedelta

import httpx

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.datetime_utils import utcnow
from app.core.db_utils import get_site_metric, set_site_metric
from app.core.health_checks import check_pipeline_health
from app.tasks.celery_app import celery

logger = logging.getLogger(__name__)

# SiteMetrics key prefix for per-condition "last alert fired" timestamps (O3).
_ALERT_STATE_PREFIX = "alert_last_fired:"


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
        cutoff = utcnow() - timedelta(days=30)

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

        logger.info(
            "Purge complete: %d clusters, %d raw_items deleted (cutoff: %s)",
            clusters_deleted, items_deleted, cutoff,
        )

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
    from app.models import Cluster, ClusterEntity, Entity

    db = SessionLocal()
    try:
        bogus = db.query(Entity).filter(
            ~Entity.name.op('~')(r'[a-zA-Z]')
        ).all()

        if not bogus:
            logger.info("No bogus entities found.")
            return {"status": "success", "deleted": 0}

        bogus_ids = {e.id for e in bogus}
        logger.info("Found %d bogus entities: %s", len(bogus_ids), [e.name for e in bogus])

        db.query(ClusterEntity).filter(
            ClusterEntity.entity_id.in_(bogus_ids)
        ).delete(synchronize_session='fetch')

        from sqlalchemy import Integer, cast
        from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
        clusters = db.query(Cluster).filter(
            Cluster.entities_agg.op('&&')(cast(list(bogus_ids), PG_ARRAY(Integer)))
        ).all()
        for cluster in clusters:
            cluster.entities_agg = [
                eid for eid in (cluster.entities_agg or [])
                if eid not in bogus_ids
            ]

        for entity in bogus:
            db.delete(entity)

        db.commit()
        logger.info("Deleted %d bogus entities and cleaned up associations.", len(bogus_ids))

        return {"status": "success", "deleted": len(bogus_ids)}

    finally:
        db.close()


def _describe_health(health) -> str:
    """Build a short human-readable summary of a degraded pipeline."""
    parts = []
    if health.ingest_stale:
        last = health.last_scan_at.isoformat() if health.last_scan_at else "never"
        parts.append(f"ingest stale (last scan: {last})")
    if health.broken_sources:
        names = ", ".join(
            f"{s['name']} ({s['fetch_error_count']} errors)"
            for s in health.broken_sources
        )
        parts.append(f"broken sources: {names}")
    return "; ".join(parts)


def _send_webhook_alert(message: str, health) -> bool:
    """POST a short JSON alert to ALERT_WEBHOOK_URL, if configured.

    The body carries both ``text`` (Slack) and ``content`` (Discord) keys plus a
    structured ``conditions`` list, so it works with ntfy/Discord/Slack-style
    receivers. Returns True if a request was sent and accepted.
    """
    url = settings.alert_webhook_url
    if not url:
        return False

    payload = {
        "text": message,
        "content": message,
        "conditions": health.conditions,
        "broken_sources": health.broken_sources,
        "last_scan_at": health.last_scan_at.isoformat() if health.last_scan_at else None,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()
        return True
    except Exception as exc:  # network/HTTP errors must not crash the task
        logger.error("Failed to POST health alert to webhook: %s", exc)
        return False


@celery.task(name="app.tasks.maintenance.monitor_pipeline_health")
def monitor_pipeline_health():
    """
    Watch the ingestion pipeline and alert on degradation (brief 09, O3).

    Flags the pipeline degraded when the newest source fetch is older than 3x
    the ingest interval, or when any approved source has hit the broken
    threshold (fetch_error_count >= 3). On a degraded condition it logs at ERROR
    and, if ALERT_WEBHOOK_URL is set, POSTs a short JSON alert — de-duplicated so
    the same condition doesn't re-fire more than once per alert_dedup_hours.

    Runs every ~30 minutes via Celery Beat.
    """
    db = SessionLocal()
    try:
        health = check_pipeline_health(db)

        if not health.degraded:
            logger.debug("Pipeline health OK")
            return {"status": "ok", "degraded": False}

        summary = _describe_health(health)
        logger.error("Pipeline degraded: %s", summary)

        # De-duplicate per condition: only alert if we haven't fired for this
        # condition within the dedup window.
        now_ts = int(utcnow().timestamp())
        dedup_seconds = settings.alert_dedup_hours * 3600
        conditions_to_alert = []
        for condition in health.conditions:
            last_fired = get_site_metric(db, _ALERT_STATE_PREFIX + condition, default=0)
            if now_ts - last_fired >= dedup_seconds:
                conditions_to_alert.append(condition)

        alert_sent = False
        if conditions_to_alert:
            message = f"Sharks aggregator pipeline degraded: {summary}"
            alert_sent = _send_webhook_alert(message, health)
            # Record the fire time regardless of webhook success so a flapping
            # condition with no webhook configured doesn't spin; the ERROR log
            # still fires every run.
            for condition in conditions_to_alert:
                set_site_metric(db, _ALERT_STATE_PREFIX + condition, now_ts)

        return {
            "status": "degraded",
            "degraded": True,
            "conditions": health.conditions,
            "alerted": conditions_to_alert,
            "webhook_sent": alert_sent,
        }

    finally:
        db.close()
