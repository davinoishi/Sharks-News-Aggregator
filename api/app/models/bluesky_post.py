"""
BlueSkyPost model - tracks posts made to BlueSky.
"""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship

from app.core.database import Base


class PostStatus(str, PyEnum):
    """Status of a BlueSky post."""
    PENDING = "pending"
    POSTED = "posted"
    FAILED = "failed"
    SKIPPED = "skipped"


class BlueSkyPost(Base):
    """
    BlueSkyPost model - tracks posts to BlueSky social media.

    Each record represents an attempt to post a cluster to BlueSky.
    Used to avoid duplicate posts and track posting history.

    Attributes:
        id: Primary key
        cluster_id: Foreign key to clusters table
        status: Post status (pending, posted, failed, skipped)
        post_uri: BlueSky post URI (at://did:plc:.../app.bsky.feed.post/...)
        post_cid: BlueSky post CID
        post_text: The text that was posted
        error_message: Error details if posting failed
        retry_count: Number of retry attempts
        posted_at: Timestamp when successfully posted
        created_at: Timestamp when record was created
    """
    __tablename__ = "bluesky_posts"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(
        Integer,
        ForeignKey("clusters.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    status = Column(
        Enum(PostStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PostStatus.PENDING
    )
    post_uri = Column(String(500), nullable=True)
    post_cid = Column(String(100), nullable=True)
    post_text = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", backref="bluesky_posts")

    def __repr__(self):
        return f"<BlueSkyPost(id={self.id}, cluster_id={self.cluster_id}, status={self.status.value})>"
