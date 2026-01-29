"""
Enrichment worker tasks for processing raw items into story variants.
Handles entity extraction, tagging, clustering, and headline generation.
"""
from typing import List, Set, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery
from app.core.database import SessionLocal
from app.core.config import settings


@celery.task(name="app.tasks.enrich.enrich_raw_item", bind=True)
def enrich_raw_item(self, raw_item_id: int):
    """
    Process a raw_item into a story_variant.
    Extracts entities, normalizes text, tags, and clusters.

    Args:
        raw_item_id: ID of the raw_item to process
    """
    from app.models import RawItem, StoryVariant, Source, EventType

    db = SessionLocal()
    try:
        # Load raw_item from database
        raw_item = db.query(RawItem).filter(RawItem.id == raw_item_id).first()
        if not raw_item:
            return {"error": "RawItem not found", "raw_item_id": raw_item_id}

        print(f"Enriching raw item {raw_item_id}: {raw_item.raw_title[:50]}...")

        # Load source for tagging and relevance check
        source = db.query(Source).filter(Source.id == raw_item.source_id).first()

        # Step 1: Extract and normalize text
        text = f"{raw_item.raw_title or ''} {raw_item.raw_description or ''}"
        tokens = normalize_tokens(text)

        # Step 2: Extract entities
        entity_ids = extract_entities(db, text)

        # Step 2.5: Check relevance unless source is dedicated to Sharks news
        source_metadata = source.extra_metadata or {}
        if not source_metadata.get('skip_relevance_check'):
            if not check_sharks_relevance(db, raw_item.raw_title or '', entity_ids):
                print(f"  ⊘ Skipped (not Sharks-relevant): {raw_item.raw_title[:50]}...")
                return {
                    "status": "skipped",
                    "reason": "not_sharks_relevant",
                    "raw_item_id": raw_item_id
                }

        # Step 3: Classify event type
        event_type_str = classify_event_type(text, entity_ids)
        event_type_enum = EventType[event_type_str.upper()] if event_type_str.upper() in EventType.__members__ else EventType.OTHER

        # Step 4: Create story_variant
        variant = StoryVariant(
            raw_item_id=raw_item.id,
            source_id=raw_item.source_id,
            title=raw_item.raw_title or "Untitled",
            url=raw_item.canonical_url,
            published_at=raw_item.published_at or datetime.utcnow(),
            event_type=event_type_enum,
            tokens=tokens,
            entities=entity_ids,
        )

        db.add(variant)
        db.flush()

        db.commit()

        # Step 5: Match or create cluster (this also handles entity and tag associations)
        cluster_id = match_or_create_cluster(db, variant, tokens, entity_ids, event_type_str, source)

        print(f"  ✓ Created variant {variant.id}, matched to cluster {cluster_id}")

        return {
            "status": "success",
            "raw_item_id": raw_item_id,
            "variant_id": variant.id,
            "cluster_id": cluster_id,
            "entities": entity_ids,
            "event_type": event_type_str
        }

    except Exception as exc:
        print(f"  ✗ Error enriching raw item {raw_item_id}: {exc}")
        db.rollback()
        raise
    finally:
        db.close()


def normalize_tokens(text: str) -> List[str]:
    """
    Normalize text into tokens for clustering.

    Steps:
    1. Lowercase
    2. Remove punctuation
    3. Remove stopwords
    4. Optional: Stemming

    Args:
        text: Raw text to normalize

    Returns:
        List of normalized tokens
    """
    import re
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize

    # Lowercase and remove punctuation
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)

    # Tokenize
    tokens = word_tokenize(text)

    # Remove stopwords
    stop_words = set(stopwords.words('english'))
    tokens = [t for t in tokens if t not in stop_words and len(t) > 2]

    # TODO: Optional stemming
    # from nltk.stem import PorterStemmer
    # stemmer = PorterStemmer()
    # tokens = [stemmer.stem(t) for t in tokens]

    return tokens


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
    import re
    from app.models import Entity

    # Load all known entities from database
    entities = db.query(Entity).all()

    full_match_ids = []
    last_name_match_ids = []
    text_lower = text.lower()

    has_sharks_context = _has_sharks_context(text_lower)

    for entity in entities:
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
    """Check if text contains Sharks-related keywords."""
    sharks_keywords = [
        'sharks', 'sj sharks', 'san jose', 'barracuda', 'sap center',
    ]
    return any(kw in text_lower for kw in sharks_keywords)


# Last names that are also common English words or very common surnames - require full name match
COMMON_WORD_NAMES = {
    # Common English words
    'white', 'brown', 'green', 'black', 'gray', 'grey', 'young', 'king',
    'cook', 'hill', 'wood', 'stone', 'rice', 'rose', 'wolf', 'fox',
    'burns', 'powers', 'waters', 'fields', 'banks', 'cross', 'church',
    'price', 'best', 'land', 'day', 'long', 'strong', 'power', 'chase',
    # Very common surnames that match other people (reporters, other players, etc.)
    'smith', 'johnson', 'jones', 'miller', 'wilson', 'moore', 'taylor',
}


def _word_boundary_match(term: str, text: str) -> bool:
    """
    Check if term appears in text with word boundaries.
    Matches "price" in "carey price scored" but not in "panarin-price-starts".
    """
    import re
    # Word boundary: start of string, whitespace, or common punctuation (but not hyphens in URLs)
    pattern = r'(?:^|[\s,.:;!?\'"()])' + re.escape(term) + r'(?:[\s,.:;!?\'"()]|$)'
    return bool(re.search(pattern, text))


def check_sharks_relevance(db: Session, title: str, entity_ids: List[int]) -> bool:
    """
    Check if content is relevant to the San Jose Sharks.

    Uses the article TITLE only for keyword matching (not description),
    because aggregator sources like Google Alerts inject unrelated
    context snippets into descriptions.

    Only player/coach/staff entities count for relevance — team entities
    are too broad (e.g. "San Jose Sharks" appearing in site navigation).

    Args:
        db: Database session
        title: Article title to check for Sharks keywords
        entity_ids: List of entity IDs found in text

    Returns:
        True if content is Sharks-relevant, False otherwise
    """
    text_lower = title.lower()

    # Direct team mentions in title
    sharks_keywords = [
        'sharks',
        'sj sharks',
        'barracuda',
        'sap center',
    ]

    if any(keyword in text_lower for keyword in sharks_keywords):
        return True

    # Only count non-team entities (players, coaches, staff) for relevance.
    # Team entities like "San Jose Sharks" can appear in site navigation
    # or sidebar text that Google Alerts injects into descriptions.
    non_team_ids = filter_team_entities(db, entity_ids)
    if non_team_ids:
        return True

    return False


def classify_event_type(text: str, entities: List[int]) -> str:
    """
    Classify the primary event type based on text content.
    Uses keyword count scoring - the category with the most keyword hits wins.

    Event types: trade, injury, lineup, recall, waiver, signing, prospect, game, opinion, other

    Args:
        text: Text to classify
        entities: Extracted entity IDs

    Returns:
        Event type string
    """
    text_lower = text.lower()

    scores = count_event_keyword_matches(text_lower)

    if not scores:
        return 'other'

    # Return the event type with the highest score
    return max(scores, key=scores.get)


def count_event_keyword_matches(text_lower: str) -> dict:
    """
    Count keyword matches for each event type category.

    Returns:
        Dict of event_type -> match count (only includes types with matches > 0)
    """
    event_keywords = {
        'trade': ['trade', 'traded', 'acquire', 'acquired', 'dealt'],
        'injury': ['injury', 'injured', 'injured reserve', 'day-to-day', 'out indefinitely', 'week-to-week'],
        'lineup': ['lineup', 'lines', 'starting', 'scratched', 'scratch'],
        'recall': ['recall', 'recalled', 'call up', 'called up', 'promote'],
        'waiver': ['waiver', 'waivers', 'claimed', 'claim'],
        'signing': ['sign', 'signed', 'contract', 'extension', 'agree to terms'],
        'prospect': ['prospect', 'draft', 'drafted', 'junior', 'development'],
        'game': ['game', 'win', 'loss', 'score', 'final', 'vs', 'defeat', 'beat',
                 'period', 'goal', 'assist', 'shutout', 'overtime', 'recap'],
        'opinion': ['think', 'believe', 'opinion', 'analysis', 'why', 'should'],
    }

    scores = {}
    for event_type, keywords in event_keywords.items():
        count = sum(1 for keyword in keywords if keyword in text_lower)
        if count > 0:
            scores[event_type] = count

    return scores


def match_or_create_cluster(
    db: Session,
    variant,
    tokens: List[str],
    entities: List[int],
    event_type: str,
    source
) -> int:
    """
    Find existing cluster or create new one for variant.
    Implements the clustering algorithm from the PRD.

    Args:
        db: Database session
        variant: Story variant object
        tokens: Normalized tokens
        entities: Entity IDs
        event_type: Classified event type

    Returns:
        cluster_id
    """
    from app.models import Cluster, ClusterVariant, ClusterStatus, EventType

    # Step 1: Determine time window based on event type
    time_window = get_time_window_for_event(event_type)
    cutoff_time = datetime.utcnow() - time_window

    # Step 2: Load candidate clusters within time window
    candidates = db.query(Cluster).filter(
        Cluster.status == ClusterStatus.ACTIVE,
        Cluster.first_seen_at >= cutoff_time
    ).all()

    # Filter out team entities for clustering (they're too broad)
    # We still store all entities on the variant, but use only player/coach/staff for matching
    clustering_entities = filter_team_entities(db, entities)

    # Step 3: Score similarity against each candidate
    best_cluster = None
    best_score = 0.0

    for cluster in candidates:
        # Get cluster's aggregated entities and tokens
        cluster_entities = cluster.entities_agg or []
        cluster_tokens = cluster.tokens or []

        # Filter team entities from cluster's aggregated entities too
        cluster_clustering_entities = filter_team_entities(db, cluster_entities)

        # Calculate scores
        E = entity_overlap_score(clustering_entities, cluster_clustering_entities)
        T = jaccard_similarity(tokens, cluster_tokens)
        K = event_compatibility_score(event_type, cluster.event_type.value)
        S = 0.55 * E + 0.35 * T + 0.10 * K

        # Check if this is a match (use clustering_entities for the gate check)
        if is_match(E, T, S, clustering_entities):
            if S > best_score + 0.000001:
                best_cluster = cluster
                best_score = S

    # Step 4: Create cluster if no match found
    if best_cluster is None:
        cluster = create_cluster(db, variant, tokens, entities, event_type, source)
    else:
        cluster = best_cluster
        # Update cluster metadata
        update_cluster_metadata(db, cluster, variant, tokens, entities, source)

    # Step 5: Link variant to cluster
    cluster_variant = ClusterVariant(
        cluster_id=cluster.id,
        variant_id=variant.id,
        similarity_score=best_score if best_cluster else 1.0
    )
    db.add(cluster_variant)

    # Update variant with cluster_id
    variant.cluster_id = cluster.id

    db.commit()

    return cluster.id


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

    from app.models import Entity

    # Get non-team entities from the provided IDs
    non_team_entities = db.query(Entity.id).filter(
        Entity.id.in_(entity_ids),
        Entity.entity_type != 'team'
    ).all()

    return [e.id for e in non_team_entities]


def entity_overlap_score(entities_v: List[int], entities_c: List[int]) -> float:
    """
    Calculate entity overlap score (E).

    E = |entities(v) ∩ entities(c)| / max(|entities(v)|, |entities(c)|)

    Uses max() to prevent large clusters (e.g., game threads with full roster)
    from matching unrelated articles that share a few common players.
    """
    if not entities_v or not entities_c:
        return 0.0

    intersection = len(set(entities_v) & set(entities_c))
    denominator = max(len(entities_v), len(entities_c))

    return intersection / denominator


def jaccard_similarity(tokens_v: List[str], tokens_c: List[str]) -> float:
    """
    Calculate Jaccard similarity score (T).

    T = |tokens(v) ∩ tokens(c)| / max(1, |tokens(v) ∪ tokens(c)|)
    """
    if not tokens_v or not tokens_c:
        return 0.0

    set_v = set(tokens_v)
    set_c = set(tokens_c)

    intersection = len(set_v & set_c)
    union = len(set_v | set_c)

    return intersection / max(1, union)


def event_compatibility_score(event_v: str, event_c: str) -> float:
    """
    Calculate event type compatibility score (K).

    K = 1.0 if exact match
    K = 0.5 if compatible
    K = 0.0 otherwise
    """
    if event_v == event_c:
        return 1.0

    # Define compatible event pairs
    compatible_pairs = {
        ('trade', 'signing'),
        ('signing', 'trade'),
        ('lineup', 'game'),
        ('game', 'lineup'),
        ('recall', 'lineup'),
        ('lineup', 'recall'),
    }

    if (event_v, event_c) in compatible_pairs:
        return 0.5

    return 0.0


def is_match(E: float, T: float, S: float, entities_v: List[int]) -> bool:
    """
    Determine if similarity scores indicate a match.

    From PRD Section 8.4:
    - Entity gate: E >= 0.50 OR (|entities(v)| == 0 AND T >= 0.40)
    - Overall score: S >= 0.62
    """
    # Entity gate
    if len(entities_v) > 0:
        entity_gate = E >= settings.entity_overlap_threshold
    else:
        entity_gate = T >= settings.token_similarity_threshold

    # Overall score gate
    score_gate = S >= settings.cluster_similarity_threshold

    return entity_gate and score_gate


def get_time_window_for_event(event_type: str) -> timedelta:
    """
    Get time window for clustering based on event type.

    From PRD:
    - 72 hours: trade, injury, lineup, recall, waiver, signing
    - 24 hours: game
    - 12 hours: opinion
    """
    if event_type in ['trade', 'injury', 'lineup', 'recall', 'waiver', 'signing', 'prospect', 'other']:
        return timedelta(hours=72)
    elif event_type == 'game':
        return timedelta(hours=24)
    elif event_type == 'opinion':
        return timedelta(hours=12)
    else:
        return timedelta(hours=72)


def create_cluster(db: Session, variant, tokens: List[str], entities: List[int], event_type: str, source):
    """
    Create a new cluster for a variant.

    Args:
        db: Database session
        variant: Story variant object
        tokens: Normalized tokens
        entities: Entity IDs
        event_type: Classified event type

    Returns:
        Cluster object
    """
    from app.models import Cluster, EventType

    event_type_enum = EventType[event_type.upper()] if event_type.upper() in EventType.__members__ else EventType.OTHER

    cluster = Cluster(
        headline=variant.title or "Untitled",
        event_type=event_type_enum,
        first_seen_at=variant.published_at or datetime.utcnow(),
        last_seen_at=variant.published_at or datetime.utcnow(),
        source_count=1,
        tokens=tokens,
        entities_agg=entities,
    )

    db.add(cluster)
    db.flush()

    # Add entity associations to cluster
    add_cluster_entity_associations(db, cluster, entities)

    # Add tag associations to cluster
    tag_names = classify_tags(variant, source)
    add_cluster_tag_associations(db, cluster, tag_names)

    return cluster


def update_cluster_metadata(db: Session, cluster, variant, tokens: List[str], entities: List[int], source):
    """
    Update cluster metadata when adding a new variant.

    Args:
        db: Database session
        cluster: Cluster object
        variant: New variant being added
        tokens: Variant's tokens
        entities: Variant's entity IDs
    """
    # Update timestamps
    cluster.last_seen_at = datetime.utcnow()

    # Update source count (will be recalculated properly in a query)
    cluster.source_count = cluster.source_count + 1

    # Merge tokens (union of existing and new)
    existing_tokens = set(cluster.tokens or [])
    new_tokens = set(tokens)
    cluster.tokens = list(existing_tokens | new_tokens)

    # Merge entities
    existing_entities = set(cluster.entities_agg or [])
    new_entities = set(entities)
    cluster.entities_agg = list(existing_entities | new_entities)

    # Add new entity associations
    add_cluster_entity_associations(db, cluster, entities)

    # Add new tag associations
    tag_names = classify_tags(variant, source)
    add_cluster_tag_associations(db, cluster, tag_names)


def get_cluster_entities(db: Session, cluster_id: int) -> List[int]:
    """Get all entity IDs associated with a cluster."""
    from app.models import ClusterEntity

    cluster_entities = db.query(ClusterEntity).filter(
        ClusterEntity.cluster_id == cluster_id
    ).all()

    return [ce.entity_id for ce in cluster_entities]


def add_cluster_entity_associations(db: Session, cluster, entity_ids: List[int]):
    """Add entity associations to a cluster."""
    from app.models import ClusterEntity

    for entity_id in entity_ids:
        # Check if association already exists
        existing = db.query(ClusterEntity).filter(
            ClusterEntity.cluster_id == cluster.id,
            ClusterEntity.entity_id == entity_id
        ).first()

        if not existing:
            cluster_entity = ClusterEntity(
                cluster_id=cluster.id,
                entity_id=entity_id
            )
            db.add(cluster_entity)


def add_cluster_tag_associations(db: Session, cluster, tag_names: List[str]):
    """Add tag associations to a cluster."""
    from app.models import ClusterTag, Tag

    for tag_name in tag_names:
        # Get or create tag
        tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if not tag:
            tag = Tag(name=tag_name, slug=Tag.make_slug(tag_name))
            db.add(tag)
            db.flush()

        # Check if association already exists
        existing = db.query(ClusterTag).filter(
            ClusterTag.cluster_id == cluster.id,
            ClusterTag.tag_id == tag.id
        ).first()

        if not existing:
            cluster_tag = ClusterTag(
                cluster_id=cluster.id,
                tag_id=tag.id
            )
            db.add(cluster_tag)


def classify_tags(variant, source) -> List[str]:
    """
    Classify tags for a variant based on content and source.
    Assigns all matching event-based tags (not just the primary event type).

    Tags: Rumors, Injury, Trade, Game, etc.
    """
    tags = []

    # Event-based tags - assign ALL matching categories, not just the primary one
    event_tag_map = {
        'trade': 'Trade',
        'injury': 'Injury',
        'lineup': 'Lineup',
        'recall': 'Recall',
        'waiver': 'Waiver',
        'signing': 'Signing',
        'prospect': 'Prospect',
        'game': 'Game',
    }

    text_lower = (variant.title or '').lower()
    matches = count_event_keyword_matches(text_lower)
    for event_key, tag_name in event_tag_map.items():
        if event_key in matches:
            tags.append(tag_name)

    # Barracuda detection (AHL affiliate)
    url_lower = (variant.url or '').lower()
    if 'barracuda' in text_lower or 'sjbarracuda' in url_lower:
        tags.append('Barracuda')

    # Rumor detection
    rumor_phrases = ['hearing', 'sources say', 'linked to', 'in talks', 'rumor', 'reportedly']

    has_rumor_language = any(phrase in text_lower for phrase in rumor_phrases)

    if has_rumor_language and source.category == 'press':
        tags.append('Rumors')

    # Official tag
    if source.category == 'official':
        tags.append('Official')

    return tags
