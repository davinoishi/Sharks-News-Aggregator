"""Tokenization, similarity scoring, and match-or-create clustering (brief 07, Q4)."""
import logging
import re
from datetime import timedelta
from difflib import SequenceMatcher
from typing import List, Optional
from urllib.parse import urlparse

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.datetime_utils import ensure_aware, utcnow
from app.enrichment.classify import classify_tags_keyword
from app.enrichment.entities import filter_team_entities
from app.enrichment.teams import extract_game_identifier
from app.models import (
    Cluster,
    ClusterEntity,
    ClusterStatus,
    ClusterTag,
    ClusterVariant,
    EventType,
    SiteMetrics,
    StoryVariant,
    Tag,
)

logger = logging.getLogger(__name__)

SYNDICATION_UUID_RE = re.compile(
    r"(?<![0-9a-f])"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    r"(?![0-9a-f])",
    re.IGNORECASE,
)


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
    # Step 1: Exact syndicated-content match. Regional publishers commonly
    # expose the same wire/video asset under different hosts while retaining a
    # shared UUID in the URL. Keep both variants, but put them on one card.
    syndication_key = extract_syndication_key(getattr(variant, "url", ""))
    if syndication_key:
        identifier = syndication_key.split(":", 1)[1]
        syndicated_cluster = (
            db.query(Cluster)
            .join(ClusterVariant, ClusterVariant.cluster_id == Cluster.id)
            .join(StoryVariant, StoryVariant.id == ClusterVariant.variant_id)
            .filter(
                Cluster.status == ClusterStatus.ACTIVE,
                StoryVariant.id != variant.id,
                StoryVariant.url.ilike(f"%{identifier}%"),
            )
            .order_by(Cluster.last_seen_at.desc())
            .first()
        )
        if syndicated_cluster:
            logger.debug(
                "  → Syndication match (%s): clustering with #%s",
                syndication_key,
                syndicated_cluster.id,
            )
            update_cluster_metadata(
                db, syndicated_cluster, variant, tokens, entities, source, tag_names
            )
            db.add(ClusterVariant(
                cluster_id=syndicated_cluster.id,
                variant_id=variant.id,
                similarity_score=1.0,
            ))
            variant.cluster_id = syndicated_cluster.id
            db.commit()
            return syndicated_cluster.id

    # Step 2: Determine time window relative to the story, not worker time.
    # A late syndicated copy of a five-day-old story should still see another
    # copy published on the same day. Using utcnow() made accepted seven-day-old
    # items ineligible for even an exact title comparison.
    time_window = get_time_window_for_event(event_type)
    variant_time = ensure_aware(variant.published_at) or utcnow()
    window_start = variant_time - time_window
    window_end = variant_time + time_window

    # Load clusters whose observed publication interval overlaps the window.
    # last_seen_at also keeps a still-evolving cluster eligible even when its
    # first article is older than the event window.
    candidates = db.query(Cluster).filter(
        Cluster.status == ClusterStatus.ACTIVE,
        Cluster.last_seen_at >= window_start,
        Cluster.first_seen_at <= window_end,
    ).all()

    # Filter out team entities for clustering (they're too broad)
    # We still store all entities on the variant, but use only player/coach/staff for matching
    clustering_entities = filter_team_entities(db, entities)

    # Step 2.3: Game-centric clustering for game events
    # Extract game identifier and check for existing cluster with same game
    game_identifier = None
    if event_type == 'game':
        text = f"{variant.title or ''}"
        game_identifier = extract_game_identifier(text, variant.published_at or utcnow())

        if game_identifier:
            # Look for existing cluster with this game identifier
            game_cluster = db.query(Cluster).filter(
                Cluster.status == ClusterStatus.ACTIVE,
                Cluster.game_identifier == game_identifier,
                Cluster.last_seen_at >= window_start,
                Cluster.first_seen_at <= window_end,
            ).first()

            if game_cluster:
                logger.debug("  → Game match (%s): clustering with #%s", game_identifier, game_cluster.id)
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
    best_title_match = None
    best_title_rank = (0.0, 0.0, 0.0)
    for cluster in candidates:
        # Get a representative title from this cluster
        cluster_title = cluster.headline
        cluster_title_normalized = normalize_title_for_matching(cluster_title)

        title_sim = title_similarity(variant_title_normalized, cluster_title_normalized)
        title_jaccard, title_containment, shared_title_tokens = title_token_similarity(
            variant_title_normalized, cluster_title_normalized
        )
        strong_containment = (
            shared_title_tokens >= settings.title_min_shared_tokens
            and title_containment >= settings.title_containment_threshold
            and title_jaccard >= settings.title_jaccard_threshold
        )
        if title_sim >= settings.title_similarity_threshold or strong_containment:
            rank = (max(title_sim, title_containment), title_jaccard, title_sim)
            if rank > best_title_rank:
                best_title_match = cluster
                best_title_rank = rank

    if best_title_match is not None:
        title_confidence = best_title_rank[0]
        logger.debug(
            "  → Title match (confidence=%.2f, jaccard=%.2f): clustering with #%s",
            title_confidence,
            best_title_rank[1],
            best_title_match.id,
        )
        update_cluster_metadata(
            db, best_title_match, variant, tokens, entities, source, tag_names
        )
        db.add(ClusterVariant(
            cluster_id=best_title_match.id,
            variant_id=variant.id,
            similarity_score=title_confidence,
        ))
        variant.cluster_id = best_title_match.id
        db.commit()
        return best_title_match.id

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
        entities_comparable = bool(clustering_entities) and bool(cluster_clustering_entities)
        llm_signal = "none"
        if has_llm_signal and cluster.llm_summary:
            L = summary_similarity(llm_summary, cluster.llm_summary)
            llm_signal = "summary_pair"
        elif has_llm_signal:
            L = summary_similarity(llm_summary, cluster.headline)
            llm_signal = "summary_headline"

        S = calculate_similarity_score(
            E, T, K, L,
            entities_comparable=entities_comparable,
            llm_signal=llm_signal,
        )

        matched = is_match(
            E, T, S, clustering_entities, L,
            entities_c=cluster_clustering_entities,
        )
        logger.debug(
            "  → Candidate #%s: E=%.3f T=%.3f K=%.3f L=%.3f S=%.3f "
            "entities_comparable=%s matched=%s",
            cluster.id, E, T, K, L, S, entities_comparable, matched,
        )

        if matched:
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


def calculate_similarity_score(
    E: float,
    T: float,
    K: float,
    L: float = 0.0,
    *,
    entities_comparable: bool,
    llm_signal: str = "none",
) -> float:
    """Combine available clustering signals without penalizing missing data.

    Previously, entity overlap retained 55% of the score even when one or both
    articles had no extracted entities. In the no-LLM case that capped an
    entity-free article at 0.45, below the 0.62 match threshold. Missing entity
    data now shifts the decision to token/event evidence instead of acting as a
    guaranteed negative.
    """
    if llm_signal == "summary_pair":
        if entities_comparable:
            return 0.35 * E + 0.20 * T + 0.10 * K + 0.35 * L
        return 0.30 * T + 0.10 * K + 0.60 * L

    if llm_signal == "summary_headline":
        if entities_comparable:
            return 0.45 * E + 0.25 * T + 0.10 * K + 0.20 * L
        return 0.55 * T + 0.15 * K + 0.30 * L

    if entities_comparable:
        return 0.55 * E + 0.35 * T + 0.10 * K

    # Renormalize the available T/K weights (0.35 + 0.10) to 1.0.
    return (0.35 * T + 0.10 * K) / 0.45


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
    if not title:
        return ""

    # Remove a trailing publication label before lowercasing so capitalization
    # remains available to the heuristic. Separators inside words (one-year,
    # Barre-Boulet) are intentionally unaffected because whitespace is required.
    suffix_match = re.search(r"\s+([-\u2013—|])\s+(.+?)\s*$", title)
    if suffix_match:
        separator, suffix = suffix_match.groups()
        suffix_words = re.findall(r"[A-Za-z0-9.]+", suffix)
        looks_like_publication = bool(suffix_words) and len(suffix_words) <= 6 and all(
            "." in word or any(char.isupper() for char in word)
            for word in suffix_words
        )
        if separator == "|" or looks_like_publication:
            title = title[:suffix_match.start()]

    # Normalize apostrophes before punctuation removal, then lowercase.
    title = title.replace("’", "'").replace("‘", "'").lower()

    # Remove punctuation
    title = re.sub(r'[^\w\s]', ' ', title)

    # Normalize whitespace
    title = ' '.join(title.split())

    return title.strip()


def title_token_similarity(title1: str, title2: str) -> tuple[float, float, int]:
    """Return headline token Jaccard, containment, and shared-token count.

    Containment catches a syndicated title with harmless editorial framing such
    as ``Sharks news:`` or ``BARRACUDA UPGRADE:``. The caller combines it with
    minimum shared-token and Jaccard gates to avoid generic short-title matches.
    """
    tokens1 = {token for token in title1.split() if len(token) > 2}
    tokens2 = {token for token in title2.split() if len(token) > 2}
    if not tokens1 or not tokens2:
        return 0.0, 0.0, 0

    shared = len(tokens1 & tokens2)
    jaccard = shared / len(tokens1 | tokens2)
    containment = shared / min(len(tokens1), len(tokens2))
    return jaccard, containment, shared


def extract_syndication_key(url: str) -> Optional[str]:
    """Extract a stable cross-domain syndicated-content key from a URL."""
    if not url:
        return None

    # Restrict fingerprints to the path. Query strings commonly contain
    # analytics/session UUIDs that identify a visit rather than an article.
    match = SYNDICATION_UUID_RE.search(urlparse(url).path)
    if not match:
        return None
    return f"uuid:{match.group(0).lower()}"


def title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two normalized titles.

    Uses SequenceMatcher for fuzzy string matching.

    Returns:
        Similarity score between 0.0 and 1.0
    """
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


def is_match(
    E: float,
    T: float,
    S: float,
    entities_v: List[int],
    L: float = 0.0,
    entities_c: Optional[List[int]] = None,
) -> bool:
    """
    Determine if similarity scores indicate a match.

    From PRD Section 8.4:
    - Entity gate: E >= 0.50 when both sides have entities
    - Missing-entity fallback: T >= 0.55 in the production matcher
    - LLM override: L >= 0.70 bypasses entity gate (high-confidence semantic match)
    - Overall score: S >= 0.62
    """
    # Entity gate
    # When both sides have entities, require entity agreement. If either side
    # lacks entity data, fall back to the token gate rather than treating the
    # missing extraction as evidence that the stories differ. ``None`` retains
    # the legacy single-list behavior for external callers.
    entities_comparable = bool(entities_v) and (
        entities_c is None or bool(entities_c)
    )
    if entities_comparable:
        entity_gate = E >= settings.entity_overlap_threshold
    else:
        token_threshold = settings.token_similarity_threshold
        if entities_c is not None:
            # The production matcher supplies both lists. Require stronger
            # lexical evidence when entity comparison is unavailable; the lower
            # legacy threshold remains for callers using the old signature.
            token_threshold = max(
                token_threshold,
                settings.entityless_token_similarity_threshold,
            )
        entity_gate = T >= token_threshold

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
    event_type_enum = EventType[event_type.upper()] if event_type.upper() in EventType.__members__ else EventType.OTHER

    llm_summary = (variant.extra_metadata or {}).get("llm_summary") if hasattr(variant, 'extra_metadata') else None

    published_at = variant.published_at or utcnow()
    cluster = Cluster(
        headline=variant.title or "Untitled",
        event_type=event_type_enum,
        first_seen_at=published_at,
        last_seen_at=published_at,
        source_count=1,
        tokens=tokens,
        entities_agg=entities,
        game_identifier=game_identifier,
        llm_summary=llm_summary,
    )

    db.add(cluster)
    db.flush()

    # Increment lifetime stories counter
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
    # but never move it backwards. Both sides are timezone-aware UTC (C2);
    # ensure_aware defends against naive values from backends without tz storage.
    variant_time = ensure_aware(variant.published_at) or utcnow()
    if variant_time > ensure_aware(cluster.last_seen_at):
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

    # Backfill a missing cluster summary when a later enrichment call succeeds.
    # The old behavior permanently left the cluster without an LLM signal if
    # OpenRouter happened to fail for the first variant.
    variant_summary = (
        (variant.extra_metadata or {}).get("llm_summary")
        if hasattr(variant, "extra_metadata") else None
    )
    if not cluster.llm_summary and variant_summary:
        cluster.llm_summary = variant_summary

    # Add new entity associations
    add_cluster_entity_associations(db, cluster, entities)

    # Add new tag associations
    if tag_names is None:
        tag_names = classify_tags_keyword(variant.title, source)
    add_cluster_tag_associations(db, cluster, tag_names)


def get_cluster_entities(db: Session, cluster_id: int) -> List[int]:
    """Get all entity IDs associated with a cluster."""
    cluster_entities = db.query(ClusterEntity).filter(
        ClusterEntity.cluster_id == cluster_id
    ).all()

    return [ce.entity_id for ce in cluster_entities]


def add_cluster_entity_associations(db: Session, cluster, entity_ids: List[int]):
    """Add entity associations to a cluster."""
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
