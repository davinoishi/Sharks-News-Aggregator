"""
Ingest worker tasks for fetching content from sources.
Handles RSS, HTML, and API-based ingestion.
"""
import hashlib
import html
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx
from celery import group
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.datetime_utils import ensure_aware, utcnow
from app.tasks.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.tasks.ingest.ingest_all_sources", bind=True)
def ingest_all_sources(self):
    """
    Master task that triggers ingestion for all approved sources.
    Runs on schedule via Celery Beat.
    """
    from app.core.db_utils import get_active_sources

    db = SessionLocal()
    try:
        # Query all approved sources
        sources = get_active_sources(db)

        if not sources:
            return {"status": "no_sources", "message": "No approved sources found"}

        # Spawn individual ingest tasks in parallel
        job = group(ingest_source.s(source.id) for source in sources)
        result = job.apply_async()

        return {
            "status": "scheduled",
            "message": f"Ingestion queued for {len(sources)} sources",
            "source_count": len(sources)
        }
    finally:
        db.close()


@celery.task(name="app.tasks.ingest.ingest_source", bind=True, max_retries=3)
def ingest_source(self, source_id: int):
    """
    Ingest content from a single source.
    Dispatches to appropriate method based on ingest_method.

    Args:
        source_id: ID of the source to ingest
    """
    from app.models import IngestMethod, Source

    db = SessionLocal()
    try:
        # Load source from database
        source = db.query(Source).filter(Source.id == source_id).first()
        if not source:
            return {"error": "Source not found", "source_id": source_id}

        # Dispatch based on ingest method
        if source.ingest_method == IngestMethod.RSS:
            result = ingest_rss(db, source)
        elif source.ingest_method == IngestMethod.HTML:
            result = ingest_html(db, source)
        elif source.ingest_method in [IngestMethod.TWITTER, IngestMethod.REDDIT, IngestMethod.API]:
            result = ingest_api(db, source)
        else:
            result = {"error": f"Unknown ingest method: {source.ingest_method}"}

        return result

    except Exception as exc:
        # Log error and retry with exponential backoff
        logger.error("Error ingesting source %s: %s", source_id, exc)
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    finally:
        db.close()


def ingest_rss(db: Session, source) -> dict:
    """
    Fetch and parse RSS feed.

    Args:
        db: Database session
        source: Source object with feed_url

    Returns:
        Dict with ingestion results
    """
    from app.core.config import settings

    try:
        logger.info("Fetching RSS feed from %s (ID: %s)", source.name, source.id)
        logger.debug("  Feed URL: %s", source.feed_url)

        # Fetch RSS feed content with httpx first (handles encoding better)
        # then pass to feedparser for parsing
        feed = None
        raw_content = None
        try:
            response = httpx.get(
                source.feed_url,
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "SharksNewsAggregator/1.0"}
            )
            response.raise_for_status()
            raw_content = response.content
            feed = feedparser.parse(raw_content)
            logger.debug("  Fetched %d bytes via httpx", len(raw_content))
        except httpx.HTTPError as fetch_err:
            # Fall back to feedparser's built-in fetcher
            logger.warning("  httpx fetch failed (%s), falling back to feedparser direct fetch", fetch_err)
            feed = feedparser.parse(source.feed_url)

        # If initial parse failed to recover entries, try sanitizing the XML
        if feed.bozo and not feed.entries and raw_content:
            logger.warning("  Initial parse failed, attempting XML sanitization...")
            sanitized = sanitize_feed_xml(raw_content)
            feed = feedparser.parse(sanitized)
            if feed.entries:
                logger.info("  Sanitization recovered %d entries", len(feed.entries))

        if feed.bozo:  # feedparser encountered an XML issue
            error_msg = str(feed.bozo_exception) if hasattr(feed, 'bozo_exception') else "Unknown RSS parse error"
            if not feed.entries:
                # Only raise if feedparser couldn't recover any entries
                logger.error("  RSS parse error (fatal): %s", error_msg)
                raise Exception(f"RSS parse error: {error_msg}")
            else:
                # Feed has minor XML issues but entries were parsed successfully
                logger.warning("  RSS parse warning (recovered %d entries): %s", len(feed.entries), error_msg)

        new_items = 0
        skipped_items = 0

        logger.info("  Found %d entries in feed", len(feed.entries))

        for entry in feed.entries:
            entry_url = resolve_entry_url(entry.get('link'), feed, source)
            entry_title = strip_html(entry.get('title'))

            # SportSpyder pages are ad wrappers — resolve to the real article
            if entry_url and 'sportspyder.com' in entry_url:
                resolved = resolve_sportspyder_url(entry_url)
                if resolved:
                    entry_url = resolved['url']
                    entry_title = resolved.get('title', entry_title)

            # Create raw_item with idempotency
            raw_item = create_raw_item(
                db=db,
                source_id=source.id,
                source_item_id=entry.get('id'),
                original_url=entry_url,
                raw_title=entry_title,
                raw_description=entry.get('summary'),
                published_at=parse_published_date(entry),
                verify_age=settings.verify_article_published_date,
            )

            if raw_item:
                new_items += 1
                # Enqueue for enrichment
                from app.tasks.enrich import enrich_raw_item
                enrich_raw_item.delay(raw_item.id)
            else:
                skipped_items += 1

        # Update source last_fetched_at
        source.last_fetched_at = utcnow()
        source.fetch_error_count = 0
        db.commit()

        logger.info("  ✓ Created %d new items, skipped %d duplicates", new_items, skipped_items)

        return {
            "status": "success",
            "source_id": source.id,
            "source_name": source.name,
            "new_items": new_items,
            "skipped_items": skipped_items
        }

    except Exception as e:
        logger.error("  ✗ Error ingesting %s: %s", source.name, e)
        source.fetch_error_count = (source.fetch_error_count or 0) + 1
        db.commit()
        raise


def _mark_source_unimplemented(db: Session, source, method: str) -> dict:
    """Hold a source out of scheduling because its ingest method is unimplemented.

    History: brief 07 (C3) replaced a silent ``not_implemented`` no-op with a
    "mark broken" path (bumping ``fetch_error_count`` to the broken threshold).
    But these sources aren't *broken* — the method is simply unsupported — so
    that produced a permanent stream of false "broken source" alerts every cycle
    (R2-F1). Instead we set a dedicated ``UNSUPPORTED`` status: ``get_active_sources``
    excludes it, so the source stops being scheduled and never trips the broken
    threshold again. ``fetch_error_count`` is intentionally left untouched.

    This is the self-healing fallback; the migration flips existing rows so the
    stub normally never runs.
    """
    from app.models import SourceStatus

    logger.warning(
        "Ingest method %s is not implemented for source %s (%s); marking unsupported "
        "and removing from the ingest schedule",
        method, source.id, source.name,
    )
    source.status = SourceStatus.UNSUPPORTED
    db.commit()
    return {
        "status": "unsupported",
        "source_id": source.id,
        "source_name": source.name,
        "reason": f"ingest_method_not_implemented:{method}",
    }


def ingest_html(db: Session, source) -> dict:
    """
    Scrape HTML content from a source.
    Requires custom selectors per source.

    Not implemented: logs a warning and marks the source broken rather than
    silently reporting success (brief 07, C3).
    """
    return _mark_source_unimplemented(db, source, "html")


def ingest_api(db: Session, source) -> dict:
    """
    Fetch content from API endpoints.
    Currently supports Reddit and potentially Twitter/YouTube APIs.

    Not implemented: logs a warning and marks the source broken rather than
    silently reporting success (brief 07, C3).
    """
    return _mark_source_unimplemented(db, source, "api")


def create_raw_item(
    db: Session,
    source_id: int,
    original_url: str,
    raw_title: Optional[str] = None,
    raw_description: Optional[str] = None,
    source_item_id: Optional[str] = None,
    published_at: Optional[datetime] = None,
    verify_age: bool = False,
) -> Optional[object]:
    """
    Create a raw_item with idempotency checks.

    Args:
        verify_age: When True (RSS ingestion), cross-check the article's own
            publication date against the feed-supplied one and reject items
            whose true date is older than ``max_article_age_days`` or that have
            no resolvable date at all. Defaults to False so other callers
            (e.g. user submissions, which are intentionally undated) are
            unaffected.

    Returns:
        RawItem object if created, None if duplicate, too old, or undated
        (when ``verify_age`` is set).
    """
    from datetime import timedelta

    from app.core.config import settings
    from app.models import RawItem

    if not original_url:
        return None

    max_age = timedelta(days=settings.max_article_age_days)

    def _too_old(when: datetime) -> bool:
        return utcnow() - ensure_aware(when) > max_age

    # Fast reject: the feed itself admits the item is old. Avoids fetching the
    # article page for items we'd discard anyway.
    if published_at and _too_old(published_at):
        return None

    # Normalize URL for deduplication
    canonical_url = normalize_url(original_url)

    # Generate ingest_hash as fallback dedup key
    content_for_hash = f"{source_id}:{canonical_url}:{raw_title or ''}"
    ingest_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()

    # Check for existing item by source_item_id or canonical_url
    existing = None
    if source_item_id:
        existing = db.query(RawItem).filter(
            RawItem.source_id == source_id,
            RawItem.source_item_id == source_item_id
        ).first()

    if not existing:
        existing = db.query(RawItem).filter(
            RawItem.canonical_url == canonical_url
        ).first()

    if not existing:
        existing = db.query(RawItem).filter(
            RawItem.ingest_hash == ingest_hash
        ).first()

    # Title-based dedup for same source (catches Google Alerts surfacing
    # the same article from different regional domains)
    if not existing and raw_title:
        existing = db.query(RawItem).filter(
            RawItem.source_id == source_id,
            RawItem.raw_title == raw_title
        ).first()

    if existing:
        return None  # Duplicate, skip

    # Authoritative age check (RSS only): the feed-supplied date can be a fresh
    # <pubDate> on a years-old article. Resolve the article's real date from its
    # own metadata and gate on that. Only runs for genuinely new, non-duplicate
    # items so we don't fetch the page on every poll.
    if verify_age:
        true_date = fetch_published_date(canonical_url)
        effective_date = true_date or published_at
        if effective_date is None:
            # Reject undated items rather than letting them default to "now" and
            # surface at the top of the feed as if breaking (D).
            logger.info("  ⊘ Rejected undated article (no feed or page date): %s", canonical_url)
            return None
        if _too_old(effective_date):
            logger.info(
                "  ⊘ Rejected stale article (true date %s past %d-day window): %s",
                effective_date.date(), settings.max_article_age_days, canonical_url,
            )
            return None
        published_at = effective_date

    # Create new raw_item
    raw_item = RawItem(
        source_id=source_id,
        source_item_id=source_item_id,
        original_url=original_url,
        canonical_url=canonical_url,
        ingest_hash=ingest_hash,
        raw_title=raw_title,
        raw_description=raw_description,
        published_at=published_at,
    )

    db.add(raw_item)
    db.commit()
    db.refresh(raw_item)

    return raw_item


def sanitize_feed_xml(content: bytes) -> bytes:
    """
    Sanitize common XML issues that cause feedparser to fail.
    Handles undefined HTML entities, encoding issues, and invalid characters.
    """
    import re

    # Decode content, trying multiple encodings
    text = None
    for encoding in ['utf-8', 'latin-1', 'windows-1252']:
        try:
            text = content.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if text is None:
        text = content.decode('utf-8', errors='replace')

    # Replace common undefined HTML entities with numeric character references
    html_entities = {
        '&nbsp;': '&#160;', '&ndash;': '&#8211;', '&mdash;': '&#8212;',
        '&lsquo;': '&#8216;', '&rsquo;': '&#8217;', '&ldquo;': '&#8220;',
        '&rdquo;': '&#8221;', '&bull;': '&#8226;', '&hellip;': '&#8230;',
        '&trade;': '&#8482;', '&copy;': '&#169;', '&reg;': '&#174;',
        '&deg;': '&#176;', '&plusmn;': '&#177;', '&times;': '&#215;',
        '&divide;': '&#247;', '&laquo;': '&#171;', '&raquo;': '&#187;',
        '&cent;': '&#162;', '&pound;': '&#163;', '&euro;': '&#8364;',
        '&frac12;': '&#189;', '&frac14;': '&#188;', '&frac34;': '&#190;',
        '&eacute;': '&#233;', '&egrave;': '&#232;', '&ecirc;': '&#234;',
        '&agrave;': '&#224;', '&acirc;': '&#226;', '&ocirc;': '&#244;',
        '&ucirc;': '&#251;', '&ccedil;': '&#231;', '&iuml;': '&#239;',
    }
    for entity, replacement in html_entities.items():
        text = text.replace(entity, replacement)

    # Remove XML-invalid control characters (except tab, newline, carriage return)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    return text.encode('utf-8')


def parse_published_date(entry: dict) -> Optional[datetime]:
    """
    Parse published date from RSS entry.
    Handles multiple date formats.
    """
    # feedparser normalizes *_parsed struct_times to UTC. We keep the existing
    # wall-clock value and tag it UTC so the result is timezone-aware (C2);
    # this matches what was previously stored when the container runs in UTC.
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        from time import mktime
        return datetime.fromtimestamp(mktime(entry.published_parsed)).replace(tzinfo=timezone.utc)
    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        from time import mktime
        return datetime.fromtimestamp(mktime(entry.updated_parsed)).replace(tzinfo=timezone.utc)
    return None


# Meta-tag attribute/value pairs that carry a publication date, in priority
# order. The first one that parses wins.
_META_DATE_KEYS = (
    ("property", "article:published_time"),
    ("property", "og:article:published_time"),
    ("name", "article:published_time"),
    ("itemprop", "datePublished"),
    ("property", "datePublished"),
    ("name", "parsely-pub-date"),
    ("name", "publishdate"),
    ("name", "publish-date"),
    ("name", "sailthru.date"),
    ("name", "date"),
    ("name", "DC.date.issued"),
)


def _parse_date_str(value: Optional[str]) -> Optional[datetime]:
    """Parse a loosely-formatted date string into an aware UTC datetime."""
    if not value or not value.strip():
        return None
    from dateutil import parser as date_parser
    try:
        parsed = date_parser.parse(value.strip())
    except (ValueError, OverflowError, TypeError):
        return None
    return ensure_aware(parsed).astimezone(timezone.utc)


def _date_from_jsonld(soup) -> Optional[datetime]:
    """Pull the first ``datePublished`` out of any JSON-LD blocks on the page."""
    import json

    def walk(node):
        if isinstance(node, dict):
            for key in ("datePublished", "dateCreated"):
                found = _parse_date_str(node.get(key)) if isinstance(node.get(key), str) else None
                if found:
                    return found
            for child in node.values():
                result = walk(child)
                if result:
                    return result
        elif isinstance(node, list):
            for child in node:
                result = walk(child)
                if result:
                    return result
        return None

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        found = walk(data)
        if found:
            return found
    return None


def extract_published_date(html_text: str) -> Optional[datetime]:
    """
    Extract an article's true publication date from its HTML.

    Checks JSON-LD (``datePublished``), then a priority list of ``<meta>`` tags,
    then a ``<time>`` element with a ``datetime`` attribute. Returns an aware UTC
    datetime, or None if no date can be found.

    Used to detect aggregator feeds that re-surface old articles with a fresh
    ``<pubDate>``: the feed date can be days old at most under the age gate, but
    the article's own metadata reveals its real age.
    """
    if not html_text:
        return None

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_text, "lxml")

    jsonld_date = _date_from_jsonld(soup)
    if jsonld_date:
        return jsonld_date

    for attr, val in _META_DATE_KEYS:
        tag = soup.find("meta", attrs={attr: val})
        if tag:
            parsed = _parse_date_str(tag.get("content"))
            if parsed:
                return parsed

    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        parsed = _parse_date_str(time_tag.get("datetime"))
        if parsed:
            return parsed

    return None


def fetch_published_date(url: str) -> Optional[datetime]:
    """
    Fetch ``url`` and extract the article's true publication date from its HTML.

    Returns None on any network/parse failure — callers treat "unknown" as a
    soft signal and fall back to the feed-supplied date. Isolated into its own
    function so the network call can be stubbed in tests.
    """
    if not url:
        return None
    try:
        response = httpx.get(
            url,
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "SharksNewsAggregator/1.0"},
        )
        response.raise_for_status()
        return extract_published_date(response.text)
    except (httpx.HTTPError, ValueError) as e:
        logger.debug("  Could not fetch article date for %s: %s", url, e)
        return None


def strip_html(text: Optional[str]) -> Optional[str]:
    """
    Strip HTML tags and decode entities from text.
    Used to clean RSS feed titles that may contain markup like <b>text</b>.
    """
    if not text:
        return text
    cleaned = re.sub(r'<[^>]+>', '', text)
    return html.unescape(cleaned).strip()


def resolve_sportspyder_url(url: str) -> Optional[dict]:
    """
    Resolve a SportSpyder wrapper URL to the real article URL.

    SportSpyder pages are JS-rendered ad wrappers with an "Open Article"
    button. Their API at /api/v1/articles/{id} returns the final_url
    and clean title.

    Returns:
        Dict with 'url' and 'title', or None on failure
    """
    import re

    match = re.search(r'/articles/(\d+)', url)
    if not match:
        return None

    article_id = match.group(1)
    try:
        resp = httpx.get(
            f"https://sportspyder.com/api/v1/articles/{article_id}",
            timeout=15.0,
            headers={"User-Agent": "SharksNewsAggregator/1.0"}
        )
        resp.raise_for_status()
        data = resp.json()

        articles = data.get("articles", [])
        if not articles:
            return None

        article = articles[0]
        final_url = article.get("final_url")
        if not final_url:
            return None

        result = {"url": final_url}
        title = article.get("title")
        if title:
            result["title"] = title

        logger.debug("  SportSpyder resolved: %s → %s", url, final_url)
        return result

    except Exception as e:
        logger.warning("  SportSpyder resolution failed for %s: %s", url, e)
        return None


def resolve_entry_url(entry_url: Optional[str], feed, source) -> Optional[str]:
    """Resolve a (possibly relative) RSS entry link to an absolute URL.

    Some feeds (e.g. the to-rss.xyz NHL.com proxy) emit relative ``<link>``
    paths like ``/sharks/news/sharks-re-sign-defenseman-nolan-allan``. Stored
    as-is, the browser resolves these against the aggregator's own origin,
    producing a broken link. Resolve them against the feed's declared channel
    link, falling back to the source's base URL.
    """
    from urllib.parse import urljoin, urlparse

    if not entry_url:
        return entry_url

    # Already absolute — leave untouched.
    if urlparse(entry_url).netloc:
        return entry_url

    # Prefer the feed's own channel <link> (carries the real publisher host),
    # then fall back to the source's configured base URL.
    base = (getattr(feed, 'feed', {}) or {}).get('link') or getattr(source, 'base_url', None)
    if base and urlparse(base).netloc:
        return urljoin(base, entry_url)

    return entry_url


def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    Removes tracking parameters, fragments, and unwraps Google redirect URLs.
    """
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    parsed = urlparse(url)

    # Unwrap Google redirect URLs (used by Google Alerts)
    # e.g. https://www.google.com/url?...&url=https%3A%2F%2Factual-site.com%2Farticle...
    if parsed.netloc in ('www.google.com', 'google.com') and parsed.path == '/url':
        query_params = parse_qs(parsed.query)
        if 'url' in query_params:
            # Re-normalize the unwrapped URL
            return normalize_url(query_params['url'][0])

    # Remove common tracking parameters
    tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'ref', 'fbclid'}
    query_params = parse_qs(parsed.query)
    cleaned_params = {k: v for k, v in query_params.items() if k not in tracking_params}

    # Rebuild URL without fragment and with cleaned params
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(cleaned_params, doseq=True),
        ''  # Remove fragment
    ))
