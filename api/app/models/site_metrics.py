"""
SiteMetrics model - simple key-value store for site-wide metrics.
"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from app.core.database import Base
from app.core.datetime_utils import utcnow


class SiteMetrics(Base):
    """
    Simple key-value store for site-wide metrics.

    Used for tracking anonymous aggregate metrics like total page views.
    No user-identifying information is stored.

    Attributes:
        key: Metric name (e.g., 'page_views')
        value: Integer value (supports large numbers)
    """
    __tablename__ = "site_metrics"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(BigInteger, default=0, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f"<SiteMetrics(key='{self.key}', value={self.value})>"
