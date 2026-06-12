"""Tests for the ops/observability features (brief 09).

Covers the SiteMetrics counter helpers (C5 fail-open metric) and the shared
pipeline-health check that backs both ``/health`` (degraded flag) and the
monitoring task (O3). These use Postgres because the metric increment relies on
``INSERT ... ON CONFLICT`` and the Source model lives in the same metadata as
the ARRAY-using models SQLite can't create.
"""
import os
from datetime import timedelta

import pytest

from app.core.datetime_utils import utcnow

DB_URL = os.environ.get("DATABASE_URL", "")
requires_postgres = pytest.mark.skipif(
    not DB_URL.startswith("postgresql"),
    reason="requires PostgreSQL (Source shares metadata with ARRAY-using models)",
)


def _make_source(db, **overrides):
    from app.models import IngestMethod, Source, SourceCategory, SourceStatus

    kwargs = dict(
        name="Test Source",
        category=SourceCategory.PRESS,
        ingest_method=IngestMethod.RSS,
        base_url="https://test.example.com",
        status=SourceStatus.APPROVED,
        last_fetched_at=utcnow(),
        fetch_error_count=0,
    )
    kwargs.update(overrides)
    src = Source(**kwargs)
    db.add(src)
    db.commit()
    return src


# --- SiteMetrics counter helpers (C5) ---------------------------------------

@requires_postgres
def test_increment_site_metric_creates_and_accumulates(pg_db):
    from app.core.db_utils import get_site_metric, increment_site_metric

    assert get_site_metric(pg_db, "llm_failopen_count") == 0
    increment_site_metric(pg_db, "llm_failopen_count")
    increment_site_metric(pg_db, "llm_failopen_count")
    assert get_site_metric(pg_db, "llm_failopen_count") == 2


@requires_postgres
def test_set_site_metric_is_absolute(pg_db):
    from app.core.db_utils import get_site_metric, set_site_metric

    set_site_metric(pg_db, "alert_last_fired:ingest_stale", 1000)
    set_site_metric(pg_db, "alert_last_fired:ingest_stale", 2000)
    assert get_site_metric(pg_db, "alert_last_fired:ingest_stale") == 2000


@requires_postgres
def test_record_llm_failopen_bumps_metric(pg_db):
    from app.core.db_utils import METRIC_LLM_FAILOPEN, get_site_metric
    from app.enrichment.classify import _record_llm_failopen

    _record_llm_failopen(pg_db, "Timeout after 45s")
    assert get_site_metric(pg_db, METRIC_LLM_FAILOPEN) == 1


# --- Pipeline health check (O3) ---------------------------------------------

@requires_postgres
def test_pipeline_health_ok(pg_db):
    from app.core.health_checks import check_pipeline_health

    _make_source(pg_db)
    health = check_pipeline_health(pg_db)
    assert health.degraded is False
    assert health.ingest_stale is False
    assert health.broken_sources == []


@requires_postgres
def test_pipeline_health_stale_ingest(pg_db):
    from app.core.health_checks import check_pipeline_health

    # Newest fetch is 2 hours ago; 3x the 10-minute interval is 30 minutes.
    _make_source(pg_db, last_fetched_at=utcnow() - timedelta(hours=2))
    health = check_pipeline_health(pg_db)
    assert health.ingest_stale is True
    assert health.degraded is True
    assert "ingest_stale" in health.conditions


@requires_postgres
def test_pipeline_health_broken_source(pg_db):
    from app.core.health_checks import check_pipeline_health

    _make_source(pg_db, fetch_error_count=5)
    health = check_pipeline_health(pg_db)
    assert health.degraded is True
    assert health.broken_sources
    assert health.broken_sources[0]["fetch_error_count"] == 5
    assert "broken_sources" in health.conditions


@requires_postgres
def test_pipeline_health_no_sources_is_stale(pg_db):
    from app.core.health_checks import check_pipeline_health

    health = check_pipeline_health(pg_db)
    # Nothing ever fetched -> treated as stale/degraded.
    assert health.ingest_stale is True
    assert health.degraded is True
