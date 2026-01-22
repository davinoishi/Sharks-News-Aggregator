"""
CandidateSource model - proposed sources awaiting review.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.source import SourceCategory, SourceStatus, IngestMethod


class CandidateSource(Base):
    """
    CandidateSource model - proposed sources for review.

    When a user submits a link from a new domain, the system
    creates a candidate source for admin review.

    Attributes:
        id: Primary key
        domain: Domain name (e.g., example.com)
        base_url: Full base URL
        discovered_from_submission_id: Original submission that found this
        suggested_category: AI/heuristic suggested category
        suggested_ingest_method: AI/heuristic suggested method
        discovered_feed_url: RSS feed if found
        rss_discovery_attempted: Whether we tried to find RSS
        rss_discovery_success: Whether RSS was found
        status: candidate/queued_for_review/approved/rejected
        evidence: Sample articles, metadata (JSON)
        review_notes: Admin notes
        reviewed_at: When reviewed
        reviewed_by: Who reviewed
    """
    __tablename__ = "candidate_sources"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), nullable=False, unique=True)
    base_url = Column(Text, nullable=False)
    discovered_from_submission_id = Column(
        Integer,
        ForeignKey("submissions.id", ondelete="SET NULL"),
        nullable=True
    )
    suggested_category = Column(Enum(SourceCategory, values_callable=lambda x: [e.value for e in x]), nullable=True)
    suggested_ingest_method = Column(Enum(IngestMethod, values_callable=lambda x: [e.value for e in x]), nullable=True)
    discovered_feed_url = Column(Text, nullable=True)
    rss_discovery_attempted = Column(Boolean, default=False)
    rss_discovery_success = Column(Boolean, default=False)
    status = Column(Enum(SourceStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=SourceStatus.CANDIDATE)
    evidence = Column(JSON, default={})
    review_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    discovered_from_submission = relationship("Submission", back_populates="candidate_sources")

    def __repr__(self):
        return f"<CandidateSource(id={self.id}, domain='{self.domain}', status={self.status})>"

    def approve_and_create_source(self, db_session, category: SourceCategory, ingest_method: IngestMethod, name: str):
        """
        Approve this candidate and create an active Source.

        Args:
            db_session: Database session
            category: Source category
            ingest_method: Ingestion method
            name: Display name for source

        Returns:
            Created Source object
        """
        from app.models.source import Source

        # Create new source
        source = Source(
            name=name,
            category=category,
            ingest_method=ingest_method,
            base_url=self.base_url,
            feed_url=self.discovered_feed_url,
            status=SourceStatus.APPROVED,
        )
        db_session.add(source)

        # Update candidate status
        self.status = SourceStatus.APPROVED
        self.reviewed_at = datetime.utcnow()

        db_session.commit()
        return source
