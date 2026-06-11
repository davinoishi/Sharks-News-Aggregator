"""Tests for the dedicated User Submissions source (submit/link FK fix)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import Source
from app.tasks.submissions import (
    USER_SUBMISSION_SOURCE_URL,
    get_or_create_user_submission_source,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Source.__table__])
    return sessionmaker(bind=engine)()


def test_creates_user_submission_source_once():
    db = _session()
    try:
        first = get_or_create_user_submission_source(db)
        again = get_or_create_user_submission_source(db)

        # Same row reused, not duplicated.
        assert first == again
        assert (
            db.query(Source)
            .filter(Source.base_url == USER_SUBMISSION_SOURCE_URL)
            .count()
            == 1
        )

        src = db.get(Source, first)
        assert src.name == "User Submissions"
        assert src.status.value == "approved"      # valid for feed display
        assert src.ingest_method.value == "api"    # ingester no-ops on it
        assert src.feed_url is None
    finally:
        db.close()
