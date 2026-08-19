"""A from-empty `alembic upgrade head` must succeed (OPS-1).

The API's command is ``alembic upgrade head && uvicorn``, so a revision that
raises does not surface as a migration error — **the service never starts**. In
CI that presented twice as a ten-minute "API did not become healthy" timeout
with no other detail.

The trap that causes it re-arms with every new revision: ``0001_baseline`` runs
``Base.metadata.create_all(checkfirst=True)`` against the *current* models, so
on an empty database it creates every table and column the code knows about
today, before any later revision runs. A bare ``op.add_column`` /
``op.create_table`` for something the baseline just made then fails.

Existing environments never hit this — the baseline ran there long ago. Only a
rebuild does: restoring the Pi after hardware failure, standing up a second
environment, onboarding from an empty database. That is the worst possible
moment to find out, which is why this runs on every commit rather than living
in a runbook.

Postgres only, and it creates and drops its own scratch database.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

DB_URL = os.environ.get("DATABASE_URL", "")
HAS_POSTGRES = DB_URL.startswith("postgresql")

pytestmark = pytest.mark.skipif(
    not HAS_POSTGRES,
    reason="requires PostgreSQL (the schema uses ARRAY columns)",
)

SCRATCH_DB = "alembic_fresh_check"
API_ROOT = Path(__file__).resolve().parents[1]


def _admin_engine():
    """Engine against the configured database, used only to CREATE/DROP another.

    CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT.
    """
    return create_engine(DB_URL, isolation_level="AUTOCOMMIT")


def _scratch_url() -> str:
    base, _, _ = DB_URL.rpartition("/")
    return f"{base}/{SCRATCH_DB}"


@pytest.fixture
def scratch_database():
    engine = _admin_engine()
    with engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    engine.dispose()
    try:
        yield _scratch_url()
    finally:
        engine = _admin_engine()
        with engine.connect() as conn:
            # Terminate stragglers so the DROP cannot block on a live session.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": SCRATCH_DB},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
        engine.dispose()


def test_alembic_upgrade_head_succeeds_on_an_empty_database(scratch_database):
    """The whole point of OPS-1: prove a rebuild would actually boot."""
    env = {**os.environ, "DATABASE_URL": scratch_database}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "alembic upgrade head failed on an empty database — a rebuilt "
        "environment would not start, because the API runs "
        "`alembic upgrade head && uvicorn`.\n\n"
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )


def test_fresh_database_reaches_the_current_head(scratch_database):
    """Not just 'no error' — it has to actually arrive at head.

    A migration chain can exit zero while stopping short (a branch, a bad
    down_revision), leaving a schema that looks migrated and is not.
    """
    env = {**os.environ, "DATABASE_URL": scratch_database}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    current = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "(head)" in current.stdout, (
        f"fresh database did not reach head:\n{current.stdout}\n{current.stderr}"
    )
