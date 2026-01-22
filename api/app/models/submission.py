"""
Submission model - user-submitted links.
"""
from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship

from app.core.database import Base


class SubmissionStatus(str, enum.Enum):
    """Submission status enum."""
    RECEIVED = "received"
    PUBLISHED = "published"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


class Submission(Base):
    """
    Submission model - user-submitted links (Option C).

    When users submit a link:
    1. Create submission record
    2. Process into raw_item and variant
    3. Cluster with existing stories
    4. Propose as candidate source if domain is new

    Attributes:
        id: Primary key
        url: Original submitted URL
        normalized_url: Cleaned URL for deduplication
        domain: Extracted domain name
        note: Optional user note
        submitter_ip: IP address for rate limiting
        status: Processing status
        raw_item_id: Created raw_item (if processed)
        variant_id: Created variant (if published)
        cluster_id: Cluster this was added to (if any)
        rejection_reason: Why this was rejected (if applicable)
        created_at: Submission timestamp
        processed_at: When processing completed
    """
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(Text, nullable=False)
    normalized_url = Column(Text, nullable=True)
    domain = Column(String(255), nullable=True)
    note = Column(Text, nullable=True)
    submitter_ip = Column(String(45), nullable=True)
    status = Column(Enum(SubmissionStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=SubmissionStatus.RECEIVED)
    raw_item_id = Column(Integer, ForeignKey("raw_items.id", ondelete="SET NULL"), nullable=True)
    variant_id = Column(Integer, ForeignKey("story_variants.id", ondelete="SET NULL"), nullable=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    raw_item = relationship("RawItem", back_populates="submissions")
    variant = relationship("StoryVariant", back_populates="submissions")
    cluster = relationship("Cluster", back_populates="submissions")
    candidate_sources = relationship("CandidateSource", back_populates="discovered_from_submission")

    def __repr__(self):
        return f"<Submission(id={self.id}, url='{self.url[:50]}...', status={self.status})>"

    def mark_processed(self, status: SubmissionStatus):
        """Mark submission as processed with given status."""
        self.status = status
        self.processed_at = datetime.utcnow()
