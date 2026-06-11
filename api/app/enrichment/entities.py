"""Entity extraction and team filtering (brief 07, Q4)."""
import re
from typing import List

from sqlalchemy.orm import Session

from app.models import Entity

# Last names that are also common English words or very common surnames -
# require full name match.
COMMON_WORD_NAMES = {
    # Common English words
    'white', 'brown', 'green', 'black', 'gray', 'grey', 'young', 'king',
    'cook', 'hill', 'wood', 'stone', 'rice', 'rose', 'wolf', 'fox',
    'burns', 'powers', 'waters', 'fields', 'banks', 'cross', 'church',
    'price', 'best', 'land', 'day', 'long', 'strong', 'power', 'chase',
    # Very common surnames that match other people (reporters, other players, etc.)
    'smith', 'johnson', 'jones', 'miller', 'wilson', 'moore', 'taylor',
}


def extract_entities(db: Session, text: str) -> List[int]:
    """
    Extract entities (players, coaches, teams) from text.

    Uses word boundary matching to avoid false positives from substrings
    appearing in URLs or compound words. Last-name-only matches require
    Sharks context in the text to avoid matching other players with the
    same surname (e.g., "Skinner" matching Jeff Skinner when the article
    is about Stuart Skinner).

    Args:
        db: Database session
        text: Text to extract entities from

    Returns:
        List of entity IDs found in text
    """
    # Load all known entities from database
    entities = db.query(Entity).all()

    full_match_ids = []
    last_name_match_ids = []
    text_lower = text.lower()

    has_sharks_context = _has_sharks_context(text_lower)

    for entity in entities:
        if not re.search(r'[a-zA-Z]', entity.name):
            continue
        name_lower = entity.name.lower()

        # Full name match (high confidence) - always accepted
        if _word_boundary_match(name_lower, text_lower):
            full_match_ids.append(entity.id)
        elif ' ' in entity.name:
            # Last-name-only match (lower confidence)
            last_name = entity.name.split()[-1].lower()
            if last_name in COMMON_WORD_NAMES:
                continue
            if len(last_name) >= 5 and _word_boundary_match(last_name, text_lower):
                last_name_match_ids.append(entity.id)

    # Only include last-name-only matches if the text mentions the Sharks
    # This prevents "Skinner" in a WHL recap from matching Jeff Skinner
    if has_sharks_context:
        return full_match_ids + last_name_match_ids
    return full_match_ids


def _has_sharks_context(text_lower: str) -> bool:
    """Check if text contains Sharks-related keywords (hockey-specific)."""
    sharks_keywords = [
        'sharks', 'sj sharks', 'san jose sharks', 'barracuda',
        'sap center', 'tech ccs arena',
    ]
    return any(kw in text_lower for kw in sharks_keywords)


def _word_boundary_match(term: str, text: str) -> bool:
    """
    Check if term appears in text with word boundaries.
    Matches "price" in "carey price scored" but not in "panarin-price-starts".
    """
    # Word boundary: start of string, whitespace, or common punctuation (but not hyphens in URLs)
    pattern = r'(?:^|[\s,.:;!?\'"()])' + re.escape(term) + r'(?:[\s,.:;!?\'"()]|$)'
    return bool(re.search(pattern, text))


def filter_team_entities(db: Session, entity_ids: List[int]) -> List[int]:
    """
    Filter out team entities from a list of entity IDs.

    Team entities (like "San Jose Sharks") are too broad for clustering -
    almost every article will have them, causing false matches.
    Only player, coach, and staff entities should be used for clustering.

    Args:
        db: Database session
        entity_ids: List of entity IDs to filter

    Returns:
        List of entity IDs excluding team entities
    """
    if not entity_ids:
        return []

    # Get non-team entities from the provided IDs
    non_team_entities = db.query(Entity.id).filter(
        Entity.id.in_(entity_ids),
        Entity.entity_type != 'team'
    ).all()

    return [e.id for e in non_team_entities]


def get_entity_names(db: Session, entity_ids: List[int]) -> str:
    """Get comma-separated entity names for LLM context."""
    if not entity_ids:
        return ""
    entities = db.query(Entity.name).filter(Entity.id.in_(entity_ids)).all()
    return ", ".join(e.name for e in entities)
