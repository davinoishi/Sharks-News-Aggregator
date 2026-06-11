"""Shared test fixtures/configuration.

Sets the required env vars before app modules import ``settings`` so
``Settings()`` can be instantiated without a real database/redis, ensures the
NLTK corpora that ``normalize_tokens`` needs are present, and provides a
Postgres session fixture for the DB-backed tests (the clustering/feed models use
ARRAY columns that SQLite can't create).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

import pytest  # noqa: E402

DB_URL = os.environ["DATABASE_URL"]
HAS_POSTGRES = DB_URL.startswith("postgresql")
requires_postgres = pytest.mark.skipif(
    not HAS_POSTGRES, reason="requires PostgreSQL (models use ARRAY columns)"
)


def _ensure_nltk():
    """Make sure normalize_tokens' corpora exist (offline-safe, download once)."""
    import nltk

    for pkg, path in (
        ("stopwords", "corpora/stopwords"),
        ("punkt", "tokenizers/punkt"),
        ("punkt_tab", "tokenizers/punkt_tab"),
    ):
        try:
            nltk.data.find(path)
        except LookupError:
            try:
                nltk.download(pkg, quiet=True)
            except Exception:
                pass


_ensure_nltk()


@pytest.fixture
def pg_db():
    """A Postgres session wrapped in a transaction that's rolled back per test."""
    if not HAS_POSTGRES:
        pytest.skip("requires PostgreSQL")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base

    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine)
    conn = engine.connect()
    trans = conn.begin()
    # create_savepoint so code-under-test calling session.commit() commits the
    # savepoint, not our outer transaction — the rollback below stays effective.
    session = sessionmaker(bind=conn, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()
        engine.dispose()
