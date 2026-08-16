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
from app.enrichment.teams import NHL_OPPONENT_TEAMS
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


# --- Sharks keyword tiers (RM-3) ---------------------------------------------
#
# "Sharks" alone is not a hockey word. At least four pro clubs carry the name
# (Sale Sharks and Cell C/Natal Sharks in rugby union, Cronulla-Sutherland in
# the NRL, plus the Jacksonville arena-football side), and the Google Alerts
# source queries the bare word. The prod failure was "Longstaff agrees to new
# deal with Sharks - Yahoo Sport", a Sale Sharks rugby story that reached the
# feed on that one token.
#
# So the keyword list is split. A STRONG keyword names San Jose unambiguously
# and approves on its own. A WEAK keyword is the ambiguous kind and needs a
# second hockey signal — which also retires two false positives recorded in
# RM-2: "AEW Forbidden Door Explodes at SAP Center" (a venue, not a team) and
# "Teal just hits different. #sharks #nhl #hockey" (hashtag chrome).
_STRONG_SHARKS_KEYWORDS = (
    'san jose sharks',
    'sj sharks',
    'sjsharks',
    'barracuda',
)

_WEAK_SHARKS_KEYWORDS = (
    'sharks',
    'sap center',
    'tech ccs arena',
)

# Terms that corroborate a weak keyword. Deliberately hockey-exclusive: shared
# sports vocabulary ('winger', 'hat trick', 'overtime', 'power play' in the
# NFL sense) would corroborate the very articles this is meant to exclude.
_HOCKEY_CONTEXT_TERMS = (
    'nhl', 'ahl', 'echl', 'hockey', 'puck', 'goalie', 'goaltender',
    'stanley cup', 'penalty kill', 'blue line', 'blueline', 'faceoff',
    'face-off', 'slapshot', 'slap shot', 'zamboni', 'icing', 'crease',
    'defenseman', 'defencemen', 'defensemen', 'winger', 'centerman',
    'teal town', 'sharkie',
)

_HOCKEY_CONTEXT_PATTERNS = tuple(
    re.compile(r'\b' + re.escape(term) + r'\b') for term in _HOCKEY_CONTEXT_TERMS
)

# "San Jose" without "Sharks" — e.g. "Longstaff agrees to new deal in San Jose".
_SAN_JOSE_PATTERN = re.compile(r'\bsan jose\b')

# Another NHL club in the title. Measured against a 741-item snapshot, this is
# the signal that saves ordinary game coverage — "Rangers at Sharks game 50",
# "Canucks Face The Sharks", "Hamilton Blocked A Trade To Sharks" — none of
# which carry hockey vocabulary, a roster player, or the city name. The table
# is reused from clustering rather than duplicated.
_NHL_TEAM_PATTERNS = tuple(
    re.compile(r'\b' + re.escape(name) + r'\b') for name in NHL_OPPONENT_TEAMS
)

# Markers that put a URL on a hockey beat. Publishers name it in the host or
# path (prohockeyrumors.com, thehockeynews.com/nhl/…, thehockeywriters).
# 'sharks' is deliberately NOT here: the rugby item's own URL contains it.
#
# 'hockey' is distinctive enough to match anywhere; the short league acronyms
# are delimited, or 'ahl' would fire on any slug containing a name like
# "Dahlin" and 'nhl' is only ever a standalone token anyway.
_HOCKEY_URL_PATTERN = re.compile(r'hockey|(?:^|[^a-z])(?:nhl|ahl|echl|puck)(?:[^a-z]|$)')

# --- Wrong-sport veto (RM-3) --------------------------------------------------
#
# Multi-word club and competition names are matched as substrings; single words
# are matched on word boundaries. Everything here is a term no ice-hockey
# headline carries, which is why the veto can outrank every approval path
# below it, entity matches included. Ambiguous words are deliberately absent:
# 'try', 'pitch', 'code', 'union', 'league' and 'football' all appear in
# ordinary hockey coverage.
_WRONG_SPORT_PHRASES = (
    'sale sharks',
    'natal sharks',
    'cell c sharks',
    'sharks rugby',
    'cronulla',
    'sharkies',
    'super rugby',
    'currie cup',
    'united rugby championship',
    'premiership rugby',
    'gallagher premiership',
    'six nations',
    'rugby championship',
    'all blacks',
    'springbok',
    'wallabies',
)

_WRONG_SPORT_WORDS = (
    'rugby', 'nrl', 'scrum', 'scrums', 'scrum-half', 'fly-half', 'flyhalf',
    'lineout', 'line-out', 'ruck', 'rucks', 'maul', 'mauls', 'tighthead',
    'loosehead', 'afl', 'cricket', 'wicket', 'batsman', 'bowler',
)

_WRONG_SPORT_WORD_PATTERNS = tuple(
    re.compile(r'\b' + re.escape(word) + r'\b') for word in _WRONG_SPORT_WORDS
)

# URL path segments publishers use to file a story by sport. A Sharks story
# never lives under one of these. '/football/' is intentionally excluded: it
# means soccer on UK sites and gridiron elsewhere, and sites that cover both
# football and hockey are common enough that the segment is not evidence.
_WRONG_SPORT_URL_SEGMENTS = (
    '/rugby/',
    '/rugby-union/',
    '/rugby-league/',
    '/rugbyunion/',
    '/nrl/',
    '/afl/',
    '/cricket/',
    '/soccer/',
)


def is_wrong_sport(title: str, url: str = "") -> bool:
    """True when the title or URL files this story under a sport that is not
    ice hockey (RM-3).

    Checked before any approval path, so a rugby story cannot be rescued by a
    keyword or an entity match. Reads the title and the URL only — never the
    description, which for the aggregator sources is page chrome (see
    ``effective_description``).
    """
    text_lower = (title or '').lower()

    if any(phrase in text_lower for phrase in _WRONG_SPORT_PHRASES):
        return True
    if any(pattern.search(text_lower) for pattern in _WRONG_SPORT_WORD_PATTERNS):
        return True

    url_lower = (url or '').lower()
    return any(segment in url_lower for segment in _WRONG_SPORT_URL_SEGMENTS)


def has_hockey_context(title: str, url: str = "", source_is_hockey: bool = False) -> bool:
    """True when something beyond an ambiguous 'Sharks' marks this as hockey.

    Any one of:

    - hockey-exclusive vocabulary in the title ("goaltender", "puck", "NHL");
    - another NHL club named in the title ("Rangers at Sharks");
    - "San Jose" in the title or URL;
    - a hockey beat visible in the URL (prohockeyrumors.com, /nhl/…);
    - a source whose whole beat is hockey (the ``hockey_scoped`` flag), for
      league-wide outlets whose headlines carry none of the above.

    The list is this long on purpose. A narrower version, measured against the
    741-item snapshot, rejected six real Sharks stories to catch one rugby one
    — headlines like "Sharks Have Big Decision To Make With Important Defender"
    genuinely carry no hockey token at all.
    """
    if source_is_hockey:
        return True

    text_lower = (title or '').lower()
    if any(pattern.search(text_lower) for pattern in _HOCKEY_CONTEXT_PATTERNS):
        return True
    if any(pattern.search(text_lower) for pattern in _NHL_TEAM_PATTERNS):
        return True

    url_lower = (url or '').lower()
    if _HOCKEY_URL_PATTERN.search(url_lower):
        return True

    return bool(
        _SAN_JOSE_PATTERN.search(text_lower)
        or _SAN_JOSE_PATTERN.search(url_lower.replace('-', ' '))
    )


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


def check_sharks_relevance(
    db: Session,
    title: str,
    entity_ids: List[int],
    url: str = "",
    source_is_hockey: bool = False,
) -> bool:
    """
    Check if content is relevant to the San Jose Sharks using keyword matching.

    Uses the article TITLE and URL only (never the description), because
    aggregator sources like Google Alerts inject unrelated context snippets
    into descriptions.

    Four gates, in order (RM-3):

    0. Wrong sport — a rugby/NRL/cricket term in the title or URL rejects
       outright, ahead of every approval path.
    1. A strong keyword (``san jose sharks``, ``barracuda``…) approves alone.
    2. A player/coach/staff entity approves alone. Team entities don't count:
       "San Jose Sharks" appears in site navigation and in the sidebar text
       Google Alerts injects. (This gate is RM-2's open leak — an off-team
       article admitted by a name — and is deliberately untouched here.)
    3. A weak keyword (bare ``sharks``, or a venue) approves only with hockey
       corroboration.

    Args:
        db: Database session
        title: Article title to check for Sharks keywords
        entity_ids: List of entity IDs found in text
        url: Canonical URL, read for sport-section path segments and "san jose"
        source_is_hockey: Source's whole beat is hockey (``hockey_scoped`` flag)

    Returns:
        True if content is Sharks-relevant, False otherwise
    """
    if is_wrong_sport(title, url):
        return False

    text_lower = title.lower()

    if any(keyword in text_lower for keyword in _STRONG_SHARKS_KEYWORDS):
        return True

    non_team_ids = filter_team_entities(db, entity_ids)
    if non_team_ids:
        return True

    if any(keyword in text_lower for keyword in _WEAK_SHARKS_KEYWORDS):
        return has_hockey_context(title, url, source_is_hockey)

    return False


def validate_sharks_relevance(
    db: Session,
    raw_item_id: int,
    title: str,
    description: str,
    entity_ids: List[int],
    url: str = "",
    source_is_hockey: bool = False,
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
        url: Canonical URL, passed through to the keyword check
        source_is_hockey: Source's whole beat is hockey (``hockey_scoped`` flag)

    Returns:
        True if article is relevant, False otherwise
    """
    # Always check keyword result
    keyword_matched = check_sharks_relevance(db, title, entity_ids, url, source_is_hockey)

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
