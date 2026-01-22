"""
FeedCache model - optional database-backed cache for feed responses.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON
from app.core.database import Base


class FeedCache(Base):
    """
    FeedCache model - optional caching table for feed responses.

    Note: Redis is the primary cache. This table is optional for
    persistent caching across Redis restarts.

    Attributes:
        id: Primary key
        cache_key: Unique cache key (query hash)
        payload: Cached feed data (JSON)
        expires_at: Expiration timestamp
        created_at: When cached
    """
    __tablename__ = "feed_cache"

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(500), nullable=False, unique=True)
    payload = Column(JSON, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __repr__(self):
        return f"<FeedCache(key='{self.cache_key}', expires={self.expires_at})>"

    @property
    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return datetime.utcnow() > self.expires_at
