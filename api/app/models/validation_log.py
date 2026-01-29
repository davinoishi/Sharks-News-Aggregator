"""
ValidationLog model - tracks LLM relevance validation decisions.
"""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Enum, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class ValidationMethod(str, PyEnum):
    """Method used for validation."""
    LLM = "llm"
    KEYWORD = "keyword"
    SKIP = "skip"


class ValidationResult(str, PyEnum):
    """Result of validation check."""
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


class ValidationLog(Base):
    """
    ValidationLog model - audit trail for article relevance validation.

    Tracks all validation decisions, whether made by LLM or fallback
    keyword matching. Enables admin review of false positives/negatives.

    Attributes:
        id: Primary key
        raw_item_id: Foreign key to raw_items table
        method: Validation method used (llm, keyword, skip)
        result: Validation result (approved, rejected, error)
        llm_response: Raw response from LLM (YES/NO/etc)
        llm_model: Model identifier used for LLM check
        keyword_matched: Whether keyword check would have matched
        entities_found: JSON list of entity IDs found in text
        reason: Human-readable explanation of decision
        latency_ms: Time taken for validation in milliseconds
        error_message: Error details if validation failed
        created_at: Timestamp of validation
    """
    __tablename__ = "validation_logs"

    id = Column(Integer, primary_key=True, index=True)
    raw_item_id = Column(
        Integer,
        ForeignKey("raw_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    method = Column(Enum(ValidationMethod), nullable=False)
    result = Column(Enum(ValidationResult), nullable=False)
    llm_response = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)
    keyword_matched = Column(Boolean, nullable=True)
    entities_found = Column(JSON, default=[])
    reason = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    # Relationships
    raw_item = relationship("RawItem", backref="validation_logs")

    def __repr__(self):
        return f"<ValidationLog(id={self.id}, raw_item_id={self.raw_item_id}, method={self.method.value}, result={self.result.value})>"
