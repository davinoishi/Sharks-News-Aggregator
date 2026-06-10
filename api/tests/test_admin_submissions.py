"""Tests for the admin submissions report endpoint."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.main import list_submissions
from app.models import Submission, SubmissionStatus


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Submission.__table__])
    return sessionmaker(bind=engine)()


def test_submissions_report_lists_and_counts():
    db = _session()
    try:
        db.add_all([
            Submission(url="https://a.example.com/x", status=SubmissionStatus.PUBLISHED),
            Submission(url="https://b.example.com/y", status=SubmissionStatus.REJECTED,
                       rejection_reason="URL not allowed"),
            Submission(url="https://a.example.com/z", status=SubmissionStatus.PUBLISHED),
        ])
        db.commit()

        result = list_submissions(status=None, limit=100, offset=0, db=db)

        assert result["total"] == 3
        assert result["by_status"]["published"] == 2
        assert result["by_status"]["rejected"] == 1
        # Newest first, domain derived from the URL when not stored.
        assert result["items"][0]["domain"] == "a.example.com"

        # Status filter narrows the page (totals reflect the filtered query).
        rejected = list_submissions(status="rejected", limit=100, offset=0, db=db)
        assert rejected["total"] == 1
        assert rejected["items"][0]["rejection_reason"] == "URL not allowed"
    finally:
        db.close()
