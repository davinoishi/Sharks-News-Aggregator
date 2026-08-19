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
from app.enrichment.teams import NHL_OPPONENT_TEAMS, extract_game_identifier
from app.models import (
    Cluster,
    ClusterEntity,
    ClusterStatus,
    ClusterTag,
    ClusterVariant,
    Entity,
    EventType,
    SiteMetrics,
    Source,
    StoryVariant,
    Tag,
)

logger = logging.getLogger(__name__)

# Hockey abbreviations that survive the short-token filter: outlets alternate
# freely between "GM" and "general manager", so both are canonicalized to the
# short form and the short form is kept as a clustering token.
SHORT_TOKENS_KEPT = frozenset({"gm"})

_GENERAL_MANAGER_RE = re.compile(r"\bgeneral manager\b")

# Words that disqualify a capitalized title bigram from being treated as a
# person name: team/city vocabulary, roles, and words routinely capitalized in
# title-case headlines. Lowercase.
_NAME_STOPWORDS = frozenset(
    {
        "san", "jose", "sharks", "barracuda", "hockey", "nhl", "ahl",
        "the", "new", "live", "updates", "update", "score", "scores",
        "game", "games", "recap", "preview", "report", "reports", "news",
        "breaking", "rumors", "watch", "hire", "hires", "hired", "sign",
        "signs", "signed", "trade", "trades", "assistant", "general",
        "manager", "coach", "head", "captain", "goalie", "goaltender",
        "defenseman", "forward", "center", "winger", "prospect",
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
    }
    | {word for keyword in NHL_OPPONENT_TEAMS for word in keyword.split()}
)

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

    # Canonicalize spelled-out abbreviations so "General Manager" and "GM"
    # produce the same token.
    text = _GENERAL_MANAGER_RE.sub("gm", text)

    # Tokenize
    tokens = word_tokenize(text)

    # Remove stopwords
    stop_words = set(stopwords.words('english'))
    tokens = [
        t for t in tokens
        if t not in stop_words and (len(t) > 2 or t in SHORT_TOKENS_KEPT)
    ]

    # TODO: Optional stemming
    # from nltk.stem import PorterStemmer
    # stemmer = PorterStemmer()
    # tokens = [stemmer.stem(t) for t in tokens]

    return tokens


def log_cluster_decision(route: str, cluster_id, variant, detail: str = "") -> None:
    """Record which route placed a variant, at INFO (CM-1).

    ``match_or_create_cluster`` has seven possible outcomes and the per-candidate
    detail is at DEBUG, which production does not retain — so an observed bad
    card could not be attributed to the route that caused it. One line per
    decision, not per candidate: a busy ingest evaluates many candidates per
    variant.
    """
    logger.info(
        "cluster_decision route=%s cluster_id=%s variant_id=%s%s",
        route,
        cluster_id,
        getattr(variant, "id", None),
        f" {detail}" if detail else "",
    )


def story_key_similarity(key_v: Optional[str], key_c: Optional[str]) -> float:
    """Compare two story_key slugs by token overlap, not string equality.

    The model emits near-misses for the same event — "celebrini-card-auction"
    against "celebrini-rookie-card-auction" — so equality would throw away most
    of the signal. Jaccard over hyphen-split parts keeps them together while
    still separating "celebrini-rookie-card-auction" from
    "sharks-pipeline-ranking".

    Returns 0.0 when either key is missing. Callers must treat that as "no
    information" rather than as a mismatch — see ``story_key_verdict``.
    """
    if not key_v or not key_c:
        return 0.0
    parts_v = {p for p in key_v.split("-") if p}
    parts_c = {p for p in key_c.split("-") if p}
    if not parts_v or not parts_c:
        return 0.0
    return len(parts_v & parts_c) / len(parts_v | parts_c)


def story_key_verdict(key_v: Optional[str], key_c: Optional[str]) -> tuple:
    """Return (verdict, score) where verdict is 'agree' | 'differ' | 'unknown'.

    Three-valued on purpose. Two keys that disagree is real evidence the
    articles are different stories — the signal RM-4 lacked entirely — but a
    *missing* key is not evidence of anything, and collapsing the two into a
    boolean is exactly how entity overlap came to act as a guaranteed negative
    (see calculate_similarity_score's docstring).
    """
    if not key_v or not key_c:
        return "unknown", 0.0
    score = story_key_similarity(key_v, key_c)
    if score >= settings.story_key_agreement_threshold:
        return "agree", score
    return "differ", score


def entity_name_tokens(db: Session, entity_ids) -> set:
    """Tokens that come from the names of ``entity_ids``.

    These are already credited by the entity-overlap score E, so counting them
    again in a token comparison double-counts the one thing two articles about
    the same player are guaranteed to share. "Macklin Celebrini Card Auction"
    and "Celebrini Tops Pipeline Rankings" have a non-trivial token overlap
    made up entirely of his name (RM-4).
    """
    ids = {int(entity_id) for entity_id in (entity_ids or [])}
    if not ids:
        return set()

    names = db.query(Entity.name).filter(Entity.id.in_(ids)).all()
    strip = set()
    for (name,) in names:
        if name:
            strip |= set(normalize_tokens(name))
    return strip


def topic_similarity(tokens_v, tokens_c, strip: set) -> float:
    """Jaccard over headline tokens with entity-derived tokens removed.

    This is the evidence that two articles are about the same *story* rather
    than about the same *person*. Returns 0.0 when either side has nothing left
    after stripping, which is the case the caller is looking for.
    """
    set_v = {t for t in tokens_v if t not in strip}
    set_c = {t for t in tokens_c if t not in strip}
    if not set_v or not set_c:
        return 0.0
    return len(set_v & set_c) / max(1, len(set_v | set_c))


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
    # Determine the time window relative to the story, not worker time. A late
    # syndicated copy of a five-day-old story should still see another copy
    # published on the same day. Using utcnow() made accepted seven-day-old
    # items ineligible for even an exact title comparison.
    time_window = get_time_window_for_event(event_type)
    variant_time = ensure_aware(variant.published_at) or utcnow()
    window_start = variant_time - time_window
    window_end = variant_time + time_window

    # Absolute ceiling on cluster age, applied to *every* match route including
    # syndication and game identity (RM-4/CM-5). Measured against the incoming
    # variant's publication time rather than wall-clock, so the pipeline stays
    # publication-relative.
    max_age_start = variant_time - timedelta(hours=settings.cluster_max_age_hours)

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
                Cluster.first_seen_at >= max_age_start,
                StoryVariant.id != variant.id,
                StoryVariant.url.ilike(f"%{identifier}%"),
            )
            .order_by(Cluster.last_seen_at.desc())
            .first()
        )
        if syndicated_cluster:
            log_cluster_decision(
                "syndication", syndicated_cluster.id, variant, detail=syndication_key
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

    # Step 2: Load candidate clusters.
    #
    # Anchored on first_seen_at, not last_seen_at (RM-4/CM-5). The old filter
    # kept a cluster eligible for 72h after its *most recent* addition, so every
    # join renewed the lease and a busy cluster never aged out — production held
    # one spanning 435 hours against a 72-hour window. A cluster's eligibility
    # now depends on when its story broke, not on how much traffic it attracts.
    candidates = db.query(Cluster).filter(
        Cluster.status == ClusterStatus.ACTIVE,
        Cluster.first_seen_at >= window_start,
        Cluster.first_seen_at >= max_age_start,
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
                Cluster.first_seen_at >= window_start,
                Cluster.first_seen_at >= max_age_start,
                Cluster.first_seen_at <= window_end,
            ).first()

            if game_cluster:
                log_cluster_decision(
                    "game", game_cluster.id, variant, detail=game_identifier
                )
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
    variant_name_keys = extract_person_name_keys(variant.title or "")

    # Compare against every title already in each candidate cluster, not just
    # the cluster's headline (its first variant's title): a rewritten headline
    # may only resemble a variant that joined the cluster later.
    candidate_titles: dict = {}
    if candidates:
        rows = (
            db.query(ClusterVariant.cluster_id, StoryVariant.title)
            .join(StoryVariant, StoryVariant.id == ClusterVariant.variant_id)
            .filter(ClusterVariant.cluster_id.in_([c.id for c in candidates]))
            .all()
        )
        for cluster_id, cluster_variant_title in rows:
            if cluster_variant_title:
                candidate_titles.setdefault(cluster_id, set()).add(cluster_variant_title)

    best_title_match = None
    best_title_rank = (0.0, 0.0, 0.0)
    best_title_route = "title"
    for cluster in candidates:
        cluster_titles = candidate_titles.get(cluster.id, set())
        if cluster.headline:
            cluster_titles = cluster_titles | {cluster.headline}
        for cluster_title in cluster_titles:
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
            # Shared person name + moderate headline overlap + compatible event
            # types. Catches personnel stories whose subject isn't in the entity
            # table yet ("Sharks Hire Jeff Kealty ..." vs "Assistant GM Jeff
            # Kealty departs Predators ..."), where every other path fails.
            name_match = False
            if variant_name_keys:
                cluster_name_keys = extract_person_name_keys(cluster_title or "")
                name_match = (
                    bool(variant_name_keys & cluster_name_keys)
                    and shared_title_tokens >= settings.title_name_min_shared_tokens
                    and title_jaccard >= settings.title_name_jaccard_threshold
                    and event_compatibility_score(event_type, cluster.event_type.value) >= 0.5
                )
            if title_sim >= settings.title_similarity_threshold or strong_containment or name_match:
                rank = (max(title_sim, title_containment), title_jaccard, title_sim)
                if rank > best_title_rank:
                    best_title_match = cluster
                    best_title_rank = rank
                    # Which of the three title tests carried it, most specific
                    # first — the routes have very different failure modes and
                    # CM-1 exists so they can be told apart in production.
                    if title_sim >= settings.title_similarity_threshold:
                        best_title_route = "title"
                    elif strong_containment:
                        best_title_route = "containment"
                    else:
                        best_title_route = "title_name"

    if best_title_match is not None:
        title_confidence = best_title_rank[0]
        log_cluster_decision(
            best_title_route,
            best_title_match.id,
            variant,
            detail=f"confidence={title_confidence:.2f} jaccard={best_title_rank[1]:.2f}",
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
    variant_story_key = (
        (variant.extra_metadata or {}).get("story_key")
        if hasattr(variant, "extra_metadata") else None
    )

    best_cluster = None
    best_score = 0.0

    # Person-name keys drawn from the LLM summary (which the classifier is
    # prompted to lead with the subject's full name). This bridges stories whose
    # headline names the subject only by role — "Sharks' first-round pick
    # finalizes plans" — to a sibling that names the person — "Keaton Verhoeff to
    # return to North Dakota". Both summaries share "keaton verhoeff", where the
    # title, entity, and lexical paths have nothing in common.
    summary_name_keys = (
        extract_person_name_keys(llm_summary or "") if has_llm_signal else set()
    )

    # Suffix-stripped headline tokens: "- Yahoo Sports"-style publication
    # labels would otherwise dilute the headline-to-headline comparison.
    variant_title_tokens = (
        normalize_tokens(normalize_title_for_matching(variant.title))
        if variant.title else []
    )

    # Tokens contributed by the variant's own entity names. Built from the
    # *unfiltered* entity list on purpose: team names ("San Jose Sharks") are
    # excluded from E by filter_team_entities, but they appear in nearly every
    # headline we ingest, so leaving them in the topical comparison would let
    # any two Sharks headlines clear the gate on the word "Sharks" alone. The
    # strip-set is completed per candidate with that cluster's entity names.
    variant_entity_tokens = entity_name_tokens(db, entities)

    best_topic_evidence = (0.0, 0.0)
    best_key = ("unknown", 0.0)
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
        # Headline-to-headline comparison: a short rewritten headline ("Sharks
        # Hire New Assistant GM") drowns in the full token pool but still
        # overlaps strongly with the cluster's headline alone.
        cluster_title_tokens = (
            normalize_tokens(normalize_title_for_matching(cluster.headline))
            if cluster.headline else []
        )
        T_title = jaccard_similarity(variant_title_tokens, cluster_title_tokens)
        T = max(T_pool, T_headline, T_title)
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

        # Shared subject name in the summaries + a compatible event type. The
        # lexical/entity signals are structurally absent when one headline hides
        # its subject behind a role ("Sharks' first-round pick finalizes plans").
        #
        # This merges on the name alone, which makes it a blanket "same person,
        # compatible event type" rule — and CLASSIFY_PROMPT_USER tells the model
        # to lead every summary with the subject's full name, so it fires on
        # nearly every pair of stories about a star player (RM-4). The topical
        # evidence gate below is what now holds it in check (CM-4).
        summary_name_match = (
            bool(summary_name_keys)
            and bool(cluster.llm_summary)
            and K >= 0.5
            and bool(summary_name_keys & extract_person_name_keys(cluster.llm_summary))
        )

        # Topical evidence: do these two articles share anything beyond the
        # people they are about? Compared against every title in the cluster,
        # not just its headline, for the same reason step 2.5 does.
        strip = variant_entity_tokens | entity_name_tokens(db, cluster_entities)
        cluster_all_titles = candidate_titles.get(cluster.id, set())
        if cluster.headline:
            cluster_all_titles = cluster_all_titles | {cluster.headline}
        T_topic = 0.0
        for cluster_title in cluster_all_titles:
            T_topic = max(T_topic, topic_similarity(
                variant_title_tokens,
                normalize_tokens(normalize_title_for_matching(cluster_title)),
                strip,
            ))

        # The same entity-strip applied to the summaries. Raw L cannot be used
        # here: the prompt's "lead with the person's full name" instruction puts
        # the name in both summaries, which is a third of a 5-10 word string, so
        # raw L separates the canonical merge-this pair from the canonical
        # don't-merge pair by 0.007 — noise, not a threshold (RM-4).
        L_topic = 0.0
        if L > 0.0 and cluster.llm_summary:
            L_topic = topic_similarity(
                normalize_tokens(normalize_title_for_matching(llm_summary)),
                normalize_tokens(normalize_title_for_matching(cluster.llm_summary)),
                strip,
            )

        # The story_key verdict. "agree" is positive topical evidence in its own
        # right; "differ" vetoes the merge outright, which is the signal no
        # lexical measure could supply — "Celebrini's card sold" and "Celebrini
        # tops the pipeline" share only his name (brief 15). "unknown" (either
        # side missing a key) falls through to the brief 14 behaviour unchanged.
        key_verdict, key_score = story_key_verdict(variant_story_key, cluster.story_key)

        # Entity overlap and event-type compatibility may corroborate a merge
        # but must never cause one. Without this, same player + same event type
        # scored 0.55*1.0 + 0.35*0.0 + 0.10*1.0 = 0.65 against a 0.62 bar and
        # merged two articles sharing no words at all (RM-4).
        topical_evidence = (
            key_verdict == "agree"
            or T_topic > settings.topic_evidence_threshold
            or L_topic >= settings.summary_evidence_threshold
        )
        if key_verdict == "differ":
            topical_evidence = False

        logger.debug(
            "  → Candidate #%s: E=%.3f T=%.3f T_topic=%.3f K=%.3f L=%.3f "
            "L_topic=%.3f S=%.3f key=%s(%.2f) entities_comparable=%s matched=%s "
            "summary_name_match=%s topical_evidence=%s",
            cluster.id, E, T, T_topic, K, L, L_topic, S, key_verdict, key_score,
            entities_comparable, matched, summary_name_match, topical_evidence,
        )

        if (matched or summary_name_match) and topical_evidence:
            if S > best_score + 0.000001:
                best_cluster = cluster
                best_score = S
                best_topic_evidence = (T_topic, L_topic)
                best_key = (key_verdict, key_score)

    # Step 4: Create cluster if no match found
    if best_cluster is None:
        cluster = create_cluster(db, variant, tokens, entities, event_type, source, game_identifier, tag_names)
        log_cluster_decision(
            "new_cluster", cluster.id, variant,
            detail=f"candidates={len(candidates)}",
        )
    else:
        cluster = best_cluster
        log_cluster_decision(
            "score", cluster.id, variant,
            detail=(
                f"S={best_score:.3f} T_topic={best_topic_evidence[0]:.3f} "
                f"L_topic={best_topic_evidence[1]:.3f} "
                f"key={best_key[0]}({best_key[1]:.2f})"
            ),
        )
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
        # Staff hires and roster moves are frequently classified 'signing' by
        # one source's wording and 'other' by another's.
        ('signing', 'other'),
        ('other', 'signing'),
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

    # Canonicalize spelled-out abbreviations ("general manager" → "gm") so
    # headline wording differences don't defeat the title comparisons.
    title = _GENERAL_MANAGER_RE.sub("gm", title)

    return title.strip()


def title_token_similarity(title1: str, title2: str) -> tuple[float, float, int]:
    """Return headline token Jaccard, containment, and shared-token count.

    Containment catches a syndicated title with harmless editorial framing such
    as ``Sharks news:`` or ``BARRACUDA UPGRADE:``. The caller combines it with
    minimum shared-token and Jaccard gates to avoid generic short-title matches.
    """
    tokens1 = {
        token for token in title1.split()
        if len(token) > 2 or token in SHORT_TOKENS_KEPT
    }
    tokens2 = {
        token for token in title2.split()
        if len(token) > 2 or token in SHORT_TOKENS_KEPT
    }
    if not tokens1 or not tokens2:
        return 0.0, 0.0, 0

    shared = len(tokens1 & tokens2)
    jaccard = shared / len(tokens1 | tokens2)
    containment = shared / min(len(tokens1), len(tokens2))
    return jaccard, containment, shared


def extract_person_name_keys(title: str) -> set:
    """Extract probable person-name bigrams from a raw (unlowercased) title.

    Personnel stories often involve people who are not yet in the entity table
    (a newly hired assistant GM, an incoming coach), which disables the entity
    clustering path entirely. Adjacent capitalized words that aren't team/city
    vocabulary or routine title-case headline words ("Sharks Hire ...") are a
    strong story-identity signal for those articles.

    Returns lowercase "first last" strings, e.g. {"jeff kealty"}.
    """
    if not title:
        return set()

    words = re.findall(r"[A-Za-z][A-Za-z'’.-]*", title)

    def looks_like_name_word(word: str) -> bool:
        # Starts uppercase and contains a lowercase letter — rejects
        # all-caps tokens like "GM" or "AHL" and lowercase sentence words.
        return word[0].isupper() and any(c.islower() for c in word)

    keys = set()
    for first, second in zip(words, words[1:]):
        if not (looks_like_name_word(first) and looks_like_name_word(second)):
            continue
        pair = (first.strip(".").lower(), second.strip(".").lower())
        if pair[0] in _NAME_STOPWORDS or pair[1] in _NAME_STOPWORDS:
            continue
        keys.add(f"{pair[0]} {pair[1]}")
    return keys


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
    tokens1 = {t for t in tokens1 if len(t) > 2 or t in SHORT_TOKENS_KEPT}
    tokens2 = {t for t in tokens2 if len(t) > 2 or t in SHORT_TOKENS_KEPT}

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

    extra = (variant.extra_metadata or {}) if hasattr(variant, 'extra_metadata') else {}
    llm_summary = extra.get("llm_summary")
    story_key = extra.get("story_key")

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
        story_key=story_key,
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


# Source authority for headline selection. A club/league page reporting a move
# outranks a rewrite of it, so it names the card when both are equally on-topic.
_HEADLINE_SOURCE_RANK = {"official": 3, "press": 2, "other": 1}

# Placeholder titles never name a card while a real title is available.
_PLACEHOLDER_TITLES = frozenset({"untitled"})


def _headline_sort_key(title: str, category, published_at, summary: Optional[str]):
    """Rank one candidate title for naming a cluster. Higher sorts first.

    Ordered by: how well the title describes the cluster's actual subject, then
    source authority, then earliest publication (the original report over a
    later aggregation).
    """
    representativeness = summary_similarity(title, summary) if summary else 0.0
    category_value = getattr(category, "value", category)
    rank = _HEADLINE_SOURCE_RANK.get(category_value, 0)

    aware = ensure_aware(published_at)
    # Negated so the *earliest* publication wins the tie-break under max();
    # an undated variant sorts last rather than winning by accident.
    recency = -aware.timestamp() if aware else float("-inf")

    return (round(representativeness, 3), rank, recency)


def select_cluster_headline(db: Session, cluster, incoming=None) -> Optional[str]:
    """Pick the title that should name ``cluster`` across all of its variants.

    The headline used to be frozen as the first variant's title, so whichever
    member happened to arrive first named the card forever — even when it was
    the least representative of the story. Re-picking over the whole membership
    is stateless (no "which variant is the headline" column to drift) and cheap:
    clusters hold a handful of variants.

    ``incoming`` is the (title, published_at, category) of a variant being added
    right now. Callers link the ClusterVariant row *after* updating metadata, so
    a new variant isn't visible to the query yet and must be passed explicitly.

    Returns None when there is no usable candidate, meaning: keep what's there.
    """
    rows = (
        db.query(StoryVariant.title, StoryVariant.published_at, Source.category)
        .join(ClusterVariant, ClusterVariant.variant_id == StoryVariant.id)
        .join(Source, Source.id == StoryVariant.source_id)
        .filter(ClusterVariant.cluster_id == cluster.id)
        # Deterministic order so equally-ranked members can't swap the headline
        # back and forth between enrichment runs.
        .order_by(StoryVariant.id)
        .all()
    )

    candidates = [(title, published_at, category) for title, published_at, category in rows if title]
    if incoming and incoming[0]:
        candidates.append(incoming)

    real_titles = [c for c in candidates if c[0].strip().lower() not in _PLACEHOLDER_TITLES]
    candidates = real_titles or candidates
    if not candidates:
        return None

    # Ties are common — summary_similarity strips publication suffixes, so
    # "X - Yahoo Sports" scores exactly like "X". Sort the incumbent headline
    # first and rely on max() returning the first maximal element, so an exact
    # tie keeps the current headline instead of churning between equals.
    incumbent = (cluster.headline or "").strip()
    candidates.sort(key=lambda c: c[0].strip() != incumbent)

    summary = getattr(cluster, "llm_summary", None)
    best = max(
        candidates,
        key=lambda c: _headline_sort_key(c[0], c[2], c[1], summary),
    )
    return best[0]


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
    variant_extra = (variant.extra_metadata or {}) if hasattr(variant, "extra_metadata") else {}
    variant_summary = variant_extra.get("llm_summary")
    if not cluster.llm_summary and variant_summary:
        cluster.llm_summary = variant_summary

    # Same backfill for story_key: a cluster whose first variant was classified
    # by the keyword fallback (or created before brief 15) has no key, and the
    # first LLM-classified member to arrive should give it one. Never overwrite
    # an existing key — the cluster's identity is set by the story it started
    # as, and letting each new member rewrite it would make the signal drift
    # exactly the way the headline used to.
    variant_key = variant_extra.get("story_key")
    if not cluster.story_key and variant_key:
        cluster.story_key = variant_key

    # Re-pick the headline across the whole membership now that the summary is
    # current. Runs after the backfill above so a cluster whose first variant
    # had no LLM summary can still rank titles by subject on this pass.
    headline = select_cluster_headline(
        db,
        cluster,
        incoming=(variant.title, variant.published_at, getattr(source, "category", None)),
    )
    if headline:
        cluster.headline = headline

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
