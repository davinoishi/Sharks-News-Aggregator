"""
Enrichment worker tasks for processing raw items into story variants.
Handles entity extraction, tagging, clustering, and headline generation.
"""
from typing import List, Set, Tuple, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery
from app.core.database import SessionLocal
from app.core.config import settings
from app.models.validation_log import ValidationLog, ValidationMethod, ValidationResult
from app.services.openrouter import (
    check_relevance as llm_check_relevance,
    classify_and_summarize as llm_classify_and_summarize,
)


# NHL opponent teams mapping (excluding Sharks)
# Maps team names and common variations to 3-letter abbreviations
NHL_OPPONENT_TEAMS = {
    'ducks': 'ANA', 'anaheim': 'ANA',
    'coyotes': 'UTA', 'utah': 'UTA',
    'bruins': 'BOS', 'boston': 'BOS',
    'sabres': 'BUF', 'buffalo': 'BUF',
    'flames': 'CGY', 'calgary': 'CGY',
    'hurricanes': 'CAR', 'carolina': 'CAR',
    'blackhawks': 'CHI', 'chicago': 'CHI',
    'avalanche': 'COL', 'colorado': 'COL',
    'blue jackets': 'CBJ', 'columbus': 'CBJ',
    'stars': 'DAL', 'dallas': 'DAL',
    'red wings': 'DET', 'detroit': 'DET',
    'oilers': 'EDM', 'edmonton': 'EDM',
    'panthers': 'FLA', 'florida': 'FLA',
    'kings': 'LAK', 'los angeles': 'LAK',
    'wild': 'MIN', 'minnesota': 'MIN',
    'canadiens': 'MTL', 'montreal': 'MTL', 'habs': 'MTL',
    'predators': 'NSH', 'nashville': 'NSH',
    'devils': 'NJD', 'new jersey': 'NJD',
    'islanders': 'NYI',
    'rangers': 'NYR',
    'senators': 'OTT', 'ottawa': 'OTT',
    'flyers': 'PHI', 'philadelphia': 'PHI',
    'penguins': 'PIT', 'pittsburgh': 'PIT',
    'kraken': 'SEA', 'seattle': 'SEA',
    'blues': 'STL', 'st louis': 'STL', 'st. louis': 'STL',
    'lightning': 'TBL', 'tampa bay': 'TBL', 'tampa': 'TBL',
    'maple leafs': 'TOR', 'toronto': 'TOR', 'leafs': 'TOR',
    'canucks': 'VAN', 'vancouver': 'VAN',
    'golden knights': 'VGK', 'vegas': 'VGK',
    'capitals': 'WSH', 'washington': 'WSH',
    'jets': 'WPG', 'winnipeg': 'WPG',
}


def extract_game_identifier(text: str, published_at: datetime) -> Optional[str]:
    """
    Extract game identifier (opponent-date) from game-related content.

    Scans text for opponent team mentions and combines with the article's
    published date to create a unique game identifier for clustering.

    Args:
        text: Article title and description combined
        published_at: Article publication timestamp

    Returns:
        Game identifier string like "LAK-2026-01-15" or None if no opponent found
    """
    text_lower = text.lower()

    # Find opponent team in text
    for keyword, team_code in NHL_OPPONENT_TEAMS.items():
        if keyword in text_lower:
            date_str = published_at.strftime('%Y-%m-%d')
            return f"{team_code}-{date_str}"

    return None


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
            validation_result = validate_sharks_relevance(
                db=db,
                raw_item_id=raw_item_id,
                title=raw_item.raw_title or '',
                description=raw_item.raw_description or '',
                entity_ids=entity_ids
            )

            if not validation_result:
                print(f"  ⊘ Skipped (not Sharks-relevant): {raw_item.raw_title[:50]}...")
                return {
                    "status": "skipped",
                    "reason": "not_sharks_relevant",
                    "raw_item_id": raw_item_id
                }
        else:
            # Log that we skipped validation for dedicated sources
            log_validation(
                db=db,
                raw_item_id=raw_item_id,
                method=ValidationMethod.SKIP,
                result=ValidationResult.APPROVED,
                reason="Source has skip_relevance_check flag",
                entity_ids=entity_ids
            )

        # Step 3: Classify event type and tags (LLM with keyword fallback)
        event_type_str, tag_names, llm_summary = classify_article(
            db, text, entity_ids, raw_item.raw_title or "", raw_item.raw_description or "",
            source, url=raw_item.canonical_url or ""
        )
        event_type_enum = EventType[event_type_str.upper()] if event_type_str.upper() in EventType.__members__ else EventType.OTHER

        # Step 4: Create story_variant
        extra_metadata = {}
        if llm_summary:
            extra_metadata["llm_summary"] = llm_summary

        variant = StoryVariant(
            raw_item_id=raw_item.id,
            source_id=raw_item.source_id,
            title=raw_item.raw_title or "Untitled",
            url=raw_item.canonical_url,
            published_at=raw_item.published_at or datetime.utcnow(),
            event_type=event_type_enum,
            tokens=tokens,
            entities=entity_ids,
            extra_metadata=extra_metadata,
        )

        db.add(variant)
        db.flush()

        db.commit()

        # Step 5: Match or create cluster (this also handles entity and tag associations)
        cluster_id = match_or_create_cluster(db, variant, tokens, entity_ids, event_type_str, source, tag_names)

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
    Check if content is relevant to the San Jose Sharks using keyword matching.

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


def validate_sharks_relevance(
    db: Session,
    raw_item_id: int,
    title: str,
    description: str,
    entity_ids: List[int]
) -> bool:
    """
    Validate article relevance using keyword matching, with optional LLM evaluation.

    Modes:
    1. LLM disabled: Keyword only
    2. LLM evaluation mode: Keyword decides, LLM evaluates for comparison report
    3. LLM enabled (not evaluation): LLM decides with keyword fallback

    Args:
        db: Database session
        raw_item_id: ID of raw_item being validated
        title: Article title
        description: Article description
        entity_ids: Entity IDs found in text

    Returns:
        True if article is relevant, False otherwise
    """
    # Always check keyword result
    keyword_matched = check_sharks_relevance(db, title, entity_ids)

    # Resolve entity names for LLM context
    entity_names = get_entity_names(db, entity_ids) if entity_ids else ""

    # If LLM is completely disabled, use keyword only
    if not settings.llm_relevance_enabled:
        log_validation(
            db=db,
            raw_item_id=raw_item_id,
            method=ValidationMethod.KEYWORD,
            result=ValidationResult.APPROVED if keyword_matched else ValidationResult.REJECTED,
            reason="LLM disabled, using keyword check",
            keyword_matched=keyword_matched,
            entity_ids=entity_ids
        )
        return keyword_matched

    # LLM Evaluation Mode: Keyword decides, LLM evaluates for reporting
    if settings.llm_evaluation_mode:
        # Run LLM in background for evaluation only
        try:
            llm_result = llm_check_relevance(title, description, entity_names)

            if llm_result.error:
                # Log evaluation with error
                agreement = "N/A (LLM error)"
            else:
                llm_relevant = llm_result.is_relevant
                if llm_relevant == keyword_matched:
                    agreement = "AGREE"
                elif keyword_matched and not llm_relevant:
                    agreement = "DISAGREE: keyword=YES, LLM=NO"
                else:
                    agreement = "DISAGREE: keyword=NO, LLM=YES"

            log_validation(
                db=db,
                raw_item_id=raw_item_id,
                method=ValidationMethod.KEYWORD,  # Keyword is the decision maker
                result=ValidationResult.APPROVED if keyword_matched else ValidationResult.REJECTED,
                llm_response=llm_result.response if not llm_result.error else None,
                llm_model=settings.openrouter_model,
                llm_confidence=llm_result.confidence,
                llm_reason=llm_result.reason,
                keyword_matched=keyword_matched,
                entity_ids=entity_ids,
                latency_ms=llm_result.latency_ms,
                error_message=llm_result.error if llm_result.error else None,
                reason=f"[EVAL MODE] {agreement} | Decision: keyword"
            )
        except Exception as e:
            log_validation(
                db=db,
                raw_item_id=raw_item_id,
                method=ValidationMethod.KEYWORD,
                result=ValidationResult.APPROVED if keyword_matched else ValidationResult.REJECTED,
                keyword_matched=keyword_matched,
                entity_ids=entity_ids,
                error_message=str(e)[:200],
                reason=f"[EVAL MODE] LLM exception | Decision: keyword"
            )

        return keyword_matched  # Keyword always decides in eval mode

    # LLM Decision Mode: LLM decides with keyword fallback
    try:
        llm_result = llm_check_relevance(title, description, entity_names)

        if llm_result.error:
            # LLM had an error, fall back to keyword check
            log_validation(
                db=db,
                raw_item_id=raw_item_id,
                method=ValidationMethod.KEYWORD,
                result=ValidationResult.APPROVED if keyword_matched else ValidationResult.REJECTED,
                llm_response=llm_result.response,
                llm_model=settings.openrouter_model,
                llm_confidence=llm_result.confidence,
                llm_reason=llm_result.reason,
                keyword_matched=keyword_matched,
                entity_ids=entity_ids,
                latency_ms=llm_result.latency_ms,
                error_message=llm_result.error,
                reason=f"LLM error, fell back to keyword: {llm_result.error[:100]}"
            )
            return keyword_matched

        # LLM succeeded
        is_relevant = llm_result.is_relevant
        log_validation(
            db=db,
            raw_item_id=raw_item_id,
            method=ValidationMethod.LLM,
            result=ValidationResult.APPROVED if is_relevant else ValidationResult.REJECTED,
            llm_response=llm_result.response,
            llm_model=settings.openrouter_model,
            llm_confidence=llm_result.confidence,
            llm_reason=llm_result.reason,
            keyword_matched=keyword_matched,
            entity_ids=entity_ids,
            latency_ms=llm_result.latency_ms,
            reason=f"LLM: {llm_result.response[:50] if llm_result.response else 'N/A'}" + (
                f" (keyword would have {'matched' if keyword_matched else 'rejected'})"
                if is_relevant != keyword_matched else ""
            )
        )
        return is_relevant

    except Exception as e:
        # Unexpected error, fall back to keyword check
        log_validation(
            db=db,
            raw_item_id=raw_item_id,
            method=ValidationMethod.KEYWORD,
            result=ValidationResult.APPROVED if keyword_matched else ValidationResult.REJECTED,
            keyword_matched=keyword_matched,
            entity_ids=entity_ids,
            error_message=str(e)[:200],
            reason=f"Exception during LLM check, fell back to keyword: {str(e)[:100]}"
        )
        return keyword_matched


def log_validation(
    db: Session,
    raw_item_id: int,
    method: ValidationMethod,
    result: ValidationResult,
    reason: Optional[str] = None,
    llm_response: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_confidence: Optional[str] = None,
    llm_reason: Optional[str] = None,
    keyword_matched: Optional[bool] = None,
    entity_ids: Optional[List[int]] = None,
    latency_ms: Optional[int] = None,
    error_message: Optional[str] = None
):
    """
    Log a validation decision to the database.

    Always commits the log entry, even if the article will be rejected.
    This provides an audit trail for admin review.
    """
    validation_log = ValidationLog(
        raw_item_id=raw_item_id,
        method=method,
        result=result,
        llm_response=llm_response,
        llm_model=llm_model,
        llm_confidence=llm_confidence,
        llm_reason=llm_reason,
        keyword_matched=keyword_matched,
        entities_found=entity_ids or [],
        reason=reason,
        latency_ms=latency_ms,
        error_message=error_message
    )
    db.add(validation_log)
    db.commit()


def classify_event_type_keyword(text: str, entities: List[int]) -> str:
    """
    Classify the primary event type based on keyword matching (fallback).
    Uses keyword count scoring - the category with the most keyword hits wins.

    Event types: trade, injury, lineup, recall, waiver, signing, prospect, game, opinion, other
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


def get_entity_names(db: Session, entity_ids: List[int]) -> str:
    """Get comma-separated entity names for LLM context."""
    if not entity_ids:
        return ""
    from app.models import Entity
    entities = db.query(Entity.name).filter(Entity.id.in_(entity_ids)).all()
    return ", ".join(e.name for e in entities)


def classify_article(
    db: Session,
    text: str,
    entity_ids: List[int],
    title: str,
    description: str,
    source,
    url: str = "",
) -> Tuple[str, List[str], Optional[str]]:
    """
    Classify event type, tags, and generate clustering summary.
    Uses LLM via OpenRouter with keyword-based fallback.

    Returns:
        Tuple of (event_type, tag_names, llm_summary)
    """
    llm_summary = None
    tag_names = []
    event_type = "other"

    if settings.llm_tagging_enabled:
        try:
            entity_names = get_entity_names(db, entity_ids)
            result = llm_classify_and_summarize(
                title[:500], description[:500], entity_names
            )
            if not result.error:
                event_type = result.event_type
                tag_names = result.tags
                llm_summary = result.summary
                print(f"  LLM classified: event={event_type}, tags={tag_names}, summary={llm_summary}")
            else:
                print(f"  LLM classification error: {result.error}, falling back to keywords")
                event_type = classify_event_type_keyword(text, entity_ids)
                tag_names = classify_tags_keyword(title, source)
        except Exception as e:
            print(f"  LLM classification exception: {e}, falling back to keywords")
            event_type = classify_event_type_keyword(text, entity_ids)
            tag_names = classify_tags_keyword(title, source)
    else:
        event_type = classify_event_type_keyword(text, entity_ids)
        tag_names = classify_tags_keyword(title, source)

    # Always apply source-based tags regardless of LLM
    if source.category == 'official' and 'Official' not in tag_names:
        tag_names.append('Official')
    url_lower = (url or '').lower()
    if ('barracuda' in title.lower() or 'sjbarracuda' in url_lower) and 'Barracuda' not in tag_names:
        tag_names.append('Barracuda')

    return event_type, tag_names, llm_summary


def match_or_create_cluster(
    db: Session,
    variant,
    tokens: List[str],
    entities: List[int],
    event_type: str,
    source,
    tag_names: Optional[List[str]] = None,
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

    # Step 2.3: Game-centric clustering for game events
    # Extract game identifier and check for existing cluster with same game
    game_identifier = None
    if event_type == 'game':
        text = f"{variant.title or ''}"
        game_identifier = extract_game_identifier(text, variant.published_at or datetime.utcnow())

        if game_identifier:
            # Look for existing cluster with this game identifier
            game_cluster = db.query(Cluster).filter(
                Cluster.status == ClusterStatus.ACTIVE,
                Cluster.game_identifier == game_identifier,
                Cluster.first_seen_at >= cutoff_time
            ).first()

            if game_cluster:
                print(f"  → Game match ({game_identifier}): clustering with #{game_cluster.id}")
                update_cluster_metadata(db, game_cluster, variant, tokens, entities, source, tag_names)
                cluster_variant = ClusterVariant(
                    cluster_id=game_cluster.id,
                    variant_id=variant.id,
                    similarity_score=1.0  # Perfect match by game ID
                )
                db.add(cluster_variant)
                variant.cluster_id = game_cluster.id
                db.commit()
                return game_cluster.id

    # Step 2.5: Check for near-identical titles (syndicated content detection)
    # This catches wire service articles republished by multiple outlets
    variant_title_normalized = normalize_title_for_matching(variant.title)
    for cluster in candidates:
        # Get a representative title from this cluster
        cluster_title = cluster.headline
        cluster_title_normalized = normalize_title_for_matching(cluster_title)

        title_sim = title_similarity(variant_title_normalized, cluster_title_normalized)
        if title_sim >= 0.85:  # 85% title similarity = likely same article
            print(f"  → Title match ({title_sim:.2f}): clustering with #{cluster.id}")
            # Auto-match to this cluster
            update_cluster_metadata(db, cluster, variant, tokens, entities, source, tag_names)
            cluster_variant = ClusterVariant(
                cluster_id=cluster.id,
                variant_id=variant.id,
                similarity_score=title_sim
            )
            db.add(cluster_variant)
            variant.cluster_id = cluster.id
            db.commit()
            return cluster.id

    # Step 3: Score similarity against each candidate
    # Use LLM summary for enhanced semantic matching when available
    llm_summary = (variant.extra_metadata or {}).get("llm_summary") if hasattr(variant, 'extra_metadata') else None
    has_llm_signal = bool(llm_summary) and settings.llm_clustering_enabled

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
        # Use max of full-pool Jaccard and headline-only Jaccard to avoid dilution
        # as clusters grow and accumulate tokens from many articles
        T_pool = jaccard_similarity(tokens, cluster_tokens)
        headline_tokens = normalize_tokens(cluster.headline) if cluster.headline else []
        T_headline = jaccard_similarity(tokens, headline_tokens)
        T = max(T_pool, T_headline)
        K = event_compatibility_score(event_type, cluster.event_type.value)

        L = 0.0
        if has_llm_signal and cluster.llm_summary:
            L = summary_similarity(llm_summary, cluster.llm_summary)
            S = 0.35 * E + 0.20 * T + 0.10 * K + 0.35 * L
        elif has_llm_signal:
            L = summary_similarity(llm_summary, cluster.headline)
            S = 0.45 * E + 0.25 * T + 0.10 * K + 0.20 * L
        else:
            S = 0.55 * E + 0.35 * T + 0.10 * K

        # Check if this is a match (use clustering_entities for the gate check)
        if is_match(E, T, S, clustering_entities, L):
            if S > best_score + 0.000001:
                best_cluster = cluster
                best_score = S

    # Step 4: Create cluster if no match found
    if best_cluster is None:
        cluster = create_cluster(db, variant, tokens, entities, event_type, source, game_identifier, tag_names)
    else:
        cluster = best_cluster
        # Update cluster metadata
        update_cluster_metadata(db, cluster, variant, tokens, entities, source, tag_names)

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
        ('opinion', 'signing'),
        ('signing', 'opinion'),
        ('opinion', 'trade'),
        ('trade', 'opinion'),
        ('opinion', 'other'),
        ('other', 'opinion'),
    }

    if (event_v, event_c) in compatible_pairs:
        return 0.5

    return 0.0


def normalize_title_for_matching(title: str) -> str:
    """
    Normalize a title for similarity matching.

    Strips common suffixes like publication names, removes punctuation,
    and lowercases to detect syndicated content.

    Examples:
        "Farabee scores winner - Western Wheel" -> "farabee scores winner"
        "Farabee scores winner | paNOW" -> "farabee scores winner"
    """
    import re

    if not title:
        return ""

    # Lowercase
    title = title.lower()

    # Remove common separators and everything after them (publication names)
    # Common patterns: " - Publication", " | Publication", " – Publication"
    title = re.split(r'\s*[-–|]\s*(?=[A-Z]|[a-z]+\.[a-z]+)', title)[0]

    # Remove punctuation
    title = re.sub(r'[^\w\s]', ' ', title)

    # Normalize whitespace
    title = ' '.join(title.split())

    return title.strip()


def title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two normalized titles.

    Uses SequenceMatcher for fuzzy string matching.

    Returns:
        Similarity score between 0.0 and 1.0
    """
    from difflib import SequenceMatcher

    if not title1 or not title2:
        return 0.0

    return SequenceMatcher(None, title1, title2).ratio()


def summary_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two LLM summaries or short texts using
    token-based Jaccard combined with SequenceMatcher.

    Takes the max of both approaches to handle:
    - Paraphrased content (Jaccard catches shared keywords regardless of order)
    - Near-identical content (SequenceMatcher catches character-level similarity)

    Returns:
        Similarity score between 0.0 and 1.0
    """
    from difflib import SequenceMatcher

    if not text1 or not text2:
        return 0.0

    norm1 = normalize_title_for_matching(text1)
    norm2 = normalize_title_for_matching(text2)

    if not norm1 or not norm2:
        return 0.0

    seq_score = SequenceMatcher(None, norm1, norm2).ratio()

    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())
    tokens1 = {t for t in tokens1 if len(t) > 2}
    tokens2 = {t for t in tokens2 if len(t) > 2}

    if tokens1 and tokens2:
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        jaccard = intersection / union
    else:
        jaccard = 0.0

    return max(seq_score, jaccard)


def is_match(E: float, T: float, S: float, entities_v: List[int], L: float = 0.0) -> bool:
    """
    Determine if similarity scores indicate a match.

    From PRD Section 8.4:
    - Entity gate: E >= 0.50 OR (|entities(v)| == 0 AND T >= 0.40)
    - LLM override: L >= 0.70 bypasses entity gate (high-confidence semantic match)
    - Overall score: S >= 0.62
    """
    # Entity gate
    if len(entities_v) > 0:
        entity_gate = E >= settings.entity_overlap_threshold
    else:
        entity_gate = T >= settings.token_similarity_threshold

    # High-confidence LLM match can bypass the entity gate
    if L >= 0.70:
        entity_gate = True

    # Overall score gate
    score_gate = S >= settings.cluster_similarity_threshold

    return entity_gate and score_gate


def get_time_window_for_event(event_type: str) -> timedelta:
    """
    Get time window for clustering based on event type.

    - 72 hours: trade, injury, lineup, recall, waiver, signing, prospect, other
    - 48 hours: opinion (analysis pieces on the same topic often span days)
    - 24 hours: game
    """
    if event_type in ['trade', 'injury', 'lineup', 'recall', 'waiver', 'signing', 'prospect', 'other']:
        return timedelta(hours=72)
    elif event_type == 'game':
        return timedelta(hours=24)
    elif event_type == 'opinion':
        return timedelta(hours=48)
    else:
        return timedelta(hours=72)


def create_cluster(
    db: Session,
    variant,
    tokens: List[str],
    entities: List[int],
    event_type: str,
    source,
    game_identifier: Optional[str] = None,
    tag_names: Optional[List[str]] = None,
):
    """
    Create a new cluster for a variant.

    Args:
        db: Database session
        variant: Story variant object
        tokens: Normalized tokens
        entities: Entity IDs
        event_type: Classified event type
        source: Source object
        game_identifier: Game identifier for game-centric clustering (e.g., "LAK-2026-01-15")

    Returns:
        Cluster object
    """
    from app.models import Cluster, EventType

    event_type_enum = EventType[event_type.upper()] if event_type.upper() in EventType.__members__ else EventType.OTHER

    llm_summary = (variant.extra_metadata or {}).get("llm_summary") if hasattr(variant, 'extra_metadata') else None

    cluster = Cluster(
        headline=variant.title or "Untitled",
        event_type=event_type_enum,
        first_seen_at=variant.published_at or datetime.utcnow(),
        last_seen_at=variant.published_at or datetime.utcnow(),
        source_count=1,
        tokens=tokens,
        entities_agg=entities,
        game_identifier=game_identifier,
        llm_summary=llm_summary,
    )

    db.add(cluster)
    db.flush()

    # Increment lifetime stories counter
    from app.models import SiteMetrics
    stories_metric = db.query(SiteMetrics).filter(SiteMetrics.key == "total_stories").first()
    if stories_metric:
        stories_metric.value += 1
    else:
        stories_metric = SiteMetrics(key="total_stories", value=1)
        db.add(stories_metric)

    # Add entity associations to cluster
    add_cluster_entity_associations(db, cluster, entities)

    # Add tag associations to cluster
    if tag_names is None:
        tag_names = classify_tags_keyword(variant.title, source)
    add_cluster_tag_associations(db, cluster, tag_names)

    return cluster


def update_cluster_metadata(db: Session, cluster, variant, tokens: List[str], entities: List[int], source, tag_names: Optional[List[str]] = None):
    """
    Update cluster metadata when adding a new variant.

    Args:
        db: Database session
        cluster: Cluster object
        variant: New variant being added
        tokens: Variant's tokens
        entities: Variant's entity IDs
    """
    # Update last_seen_at to the variant's publication date if available,
    # but never move it backwards
    variant_time = variant.published_at or datetime.utcnow()
    if variant_time.tzinfo:
        variant_time = variant_time.replace(tzinfo=None)
    if variant_time > cluster.last_seen_at.replace(tzinfo=None):
        cluster.last_seen_at = variant_time

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
    if tag_names is None:
        tag_names = classify_tags_keyword(variant.title, source)
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


def classify_tags_keyword(title: str, source) -> List[str]:
    """
    Classify tags based on keyword matching (fallback).
    Assigns all matching event-based tags (not just the primary event type).
    """
    tags = []

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

    text_lower = (title or '').lower()
    matches = count_event_keyword_matches(text_lower)
    for event_key, tag_name in event_tag_map.items():
        if event_key in matches:
            tags.append(tag_name)

    # Rumor detection
    rumor_phrases = ['hearing', 'sources say', 'linked to', 'in talks', 'rumor', 'reportedly']
    has_rumor_language = any(phrase in text_lower for phrase in rumor_phrases)
    if has_rumor_language and source.category == 'press':
        tags.append('Rumors')

    return tags
