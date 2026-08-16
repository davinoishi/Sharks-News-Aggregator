"""Relevance, event-type, and tag classification (brief 07, Q4).

Keyword scoring with LLM (OpenRouter) orchestration and keyword fallback.
"""
import logging
import re
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db_utils import METRIC_LLM_FAILOPEN, increment_site_metric
from app.enrichment.entities import filter_team_entities, get_entity_names
from app.models.validation_log import ValidationLog, ValidationMethod, ValidationResult
from app.services.openrouter import check_relevance as llm_check_relevance
from app.services.openrouter import classify_and_summarize as llm_classify_and_summarize

logger = logging.getLogger(__name__)

# Event-type keyword vocabulary. Matched as whole words: the old substring
# matching classified any headline containing "Assistant" as a game story
# ('assist') and anything from Predlines as a lineup story ('lines'), which
# then blocked clustering via the event-compatibility gate. Inflected forms
# are listed explicitly because word boundaries end stem matching.
_EVENT_KEYWORDS = {
    'trade': ['trade', 'trades', 'traded', 'acquire', 'acquires', 'acquired', 'dealt'],
    'injury': ['injury', 'injuries', 'injured', 'injured reserve', 'day-to-day',
               'out indefinitely', 'week-to-week'],
    'lineup': ['lineup', 'lineups', 'lines', 'starting', 'scratched', 'scratch', 'scratches'],
    'recall': ['recall', 'recalls', 'recalled', 'call up', 'calls up', 'called up',
               'promote', 'promotes', 'promoted'],
    'waiver': ['waiver', 'waivers', 'claim', 'claims', 'claimed'],
    'signing': ['sign', 'signs', 'signed', 'signing', 'signings', 're-sign', 're-signs',
                're-signed', 'contract', 'extension', 'agree to terms',
                'hire', 'hires', 'hired', 'hiring'],
    'prospect': ['prospect', 'prospects', 'draft', 'drafted', 'junior', 'development'],
    'game': ['game', 'games', 'win', 'wins', 'won', 'winner', 'winning', 'loss',
             'score', 'scores', 'scored', 'final', 'vs', 'defeat', 'defeats', 'defeated',
             'beat', 'beats', 'period', 'goal', 'goals', 'assist', 'assists',
             'shutout', 'overtime', 'recap'],
    'opinion': ['think', 'believe', 'opinion', 'analysis', 'why', 'should'],
}

_EVENT_KEYWORD_PATTERNS = {
    event_type: [re.compile(r'\b' + re.escape(keyword) + r'\b') for keyword in keywords]
    for event_type, keywords in _EVENT_KEYWORDS.items()
}


def _record_llm_failopen(db: Session, error: Optional[str]) -> None:
    """Surface a fail-open: the LLM relevance check errored and we fell back to
    keyword matching (brief 09, C5).

    Without this, an OpenRouter outage degrades the relevance filter silently.
    Logs at WARNING and bumps the ``llm_failopen_count`` metric so the admin
    stats endpoint and any operator dashboards can see the LLM is down.
    """
    logger.warning("LLM relevance check failed open (fell back to keyword): %s", error)
    try:
        increment_site_metric(db, METRIC_LLM_FAILOPEN)
    except Exception:  # pragma: no cover - metric must never break enrichment
        logger.exception("Failed to record llm_failopen_count metric")


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

    # Direct team mentions in title (hockey-specific only)
    sharks_keywords = [
        'sharks',
        'sj sharks',
        'san jose sharks',
        'barracuda',
        'sap center',
        'tech ccs arena',
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
                _record_llm_failopen(db, llm_result.error)
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
                reason="[EVAL MODE] LLM exception | Decision: keyword"
            )
            _record_llm_failopen(db, str(e)[:200])

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
            _record_llm_failopen(db, llm_result.error)
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
        _record_llm_failopen(db, str(e)[:200])
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
    scores = {}
    for event_type, patterns in _EVENT_KEYWORD_PATTERNS.items():
        count = sum(1 for pattern in patterns if pattern.search(text_lower))
        if count > 0:
            scores[event_type] = count

    return scores


def classify_article(
    db: Session,
    text: str,
    entity_ids: List[int],
    title: str,
    description: str,
    source,
    url: str = "",
) -> Tuple[str, List[str], Optional[str], bool]:
    """
    Classify event type, tags, and generate clustering summary.
    Uses LLM via OpenRouter with keyword-based fallback.

    Returns:
        Tuple of (event_type, tag_names, llm_summary, low_value).
        low_value is the LLM's judgment that the page is a machine-generated
        stub (streaming promo, score widget, odds page). It complements the
        keyword filter at ingest (is_scoreboard_stub) — the LLM catches
        phrasings the marker list has never seen. Fail-open: False whenever
        the LLM is disabled or errors.
    """
    llm_summary = None
    tag_names = []
    event_type = "other"
    low_value = False

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
                low_value = result.low_value
                logger.info(
                    "  LLM classified: event=%s, tags=%s, summary=%s, low_value=%s",
                    event_type, tag_names, llm_summary, low_value,
                )
            else:
                logger.warning("  LLM classification error: %s, falling back to keywords", result.error)
                event_type = classify_event_type_keyword(text, entity_ids)
                tag_names = classify_tags_keyword(title, source)
        except Exception as e:
            logger.warning("  LLM classification exception: %s, falling back to keywords", e)
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

    return event_type, tag_names, llm_summary, low_value


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
