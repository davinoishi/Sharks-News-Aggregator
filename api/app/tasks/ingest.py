"""
Ingest worker tasks for fetching content from sources.
Handles RSS, HTML, and API-based ingestion.
"""
import hashlib
from datetime import datetime
from typing import List, Optional
import feedparser
import httpx
from bs4 import BeautifulSoup
from celery import group
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery
from app.core.database import SessionLocal
from app.core.config import settings


@celery.task(name="app.tasks.ingest.ingest_all_sources", bind=True)
def ingest_all_sources(self):
    """
    Master task that triggers ingestion for all approved sources.
    Runs on schedule via Celery Beat.
    """
    from app.models import Source, SourceStatus
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
    from app.models import Source, IngestMethod

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
        print(f"Error ingesting source {source_id}: {exc}")
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
    try:
        print(f"Fetching RSS feed from {source.name} (ID: {source.id})")
        print(f"  Feed URL: {source.feed_url}")

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
            print(f"  Fetched {len(raw_content)} bytes via httpx")
        except httpx.HTTPError as fetch_err:
            # Fall back to feedparser's built-in fetcher
            print(f"  httpx fetch failed ({fetch_err}), falling back to feedparser direct fetch")
            feed = feedparser.parse(source.feed_url)

        # If initial parse failed to recover entries, try sanitizing the XML
        if feed.bozo and not feed.entries and raw_content:
            print(f"  Initial parse failed, attempting XML sanitization...")
            sanitized = sanitize_feed_xml(raw_content)
            feed = feedparser.parse(sanitized)
            if feed.entries:
                print(f"  Sanitization recovered {len(feed.entries)} entries")

        if feed.bozo:  # feedparser encountered an XML issue
            error_msg = str(feed.bozo_exception) if hasattr(feed, 'bozo_exception') else "Unknown RSS parse error"
            if not feed.entries:
                # Only raise if feedparser couldn't recover any entries
                print(f"  RSS parse error (fatal): {error_msg}")
                raise Exception(f"RSS parse error: {error_msg}")
            else:
                # Feed has minor XML issues but entries were parsed successfully
                print(f"  RSS parse warning (recovered {len(feed.entries)} entries): {error_msg}")

        new_items = 0
        skipped_items = 0

        print(f"  Found {len(feed.entries)} entries in feed")

        for entry in feed.entries:
            # Create raw_item with idempotency
            raw_item = create_raw_item(
                db=db,
                source_id=source.id,
                source_item_id=entry.get('id'),
                original_url=entry.get('link'),
                raw_title=entry.get('title'),
                raw_description=entry.get('summary'),
                published_at=parse_published_date(entry),
            )

            if raw_item:
                new_items += 1
                # Enqueue for enrichment
                from app.tasks.enrich import enrich_raw_item
                enrich_raw_item.delay(raw_item.id)
            else:
                skipped_items += 1

        # Update source last_fetched_at
        source.last_fetched_at = datetime.utcnow()
        source.fetch_error_count = 0
        db.commit()

        print(f"  ✓ Created {new_items} new items, skipped {skipped_items} duplicates")

        return {
            "status": "success",
            "source_id": source.id,
            "source_name": source.name,
            "new_items": new_items,
            "skipped_items": skipped_items
        }

    except Exception as e:
        print(f"  ✗ Error: {e}")
        source.fetch_error_count = (source.fetch_error_count or 0) + 1
        db.commit()
        raise


def ingest_html(db: Session, source) -> dict:
    """
    Scrape HTML content from a source.
    Requires custom selectors per source.

    Args:
        db: Database session
        source: Source object with base_url and metadata containing selectors

    Returns:
        Dict with ingestion results
    """
    # TODO: Implement HTML scraping with BeautifulSoup
    # This requires custom selectors per source stored in source.metadata
    return {"status": "not_implemented"}


def ingest_api(db: Session, source) -> dict:
    """
    Fetch content from API endpoints.
    Currently supports Reddit and potentially Twitter/YouTube APIs.

    Args:
        db: Database session
        source: Source object with API configuration in metadata

    Returns:
        Dict with ingestion results
    """
    # TODO: Implement API-based ingestion
    return {"status": "not_implemented"}


def create_raw_item(
    db: Session,
    source_id: int,
    original_url: str,
    raw_title: Optional[str] = None,
    raw_description: Optional[str] = None,
    source_item_id: Optional[str] = None,
    published_at: Optional[datetime] = None,
) -> Optional[object]:
    """
    Create a raw_item with idempotency checks.

    Returns:
        RawItem object if created, None if duplicate
    """
    from app.models import RawItem

    if not original_url:
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

    if existing:
        return None  # Duplicate, skip

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
    # Try published_parsed, then updated_parsed
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        from time import mktime
        return datetime.fromtimestamp(mktime(entry.published_parsed))
    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        from time import mktime
        return datetime.fromtimestamp(mktime(entry.updated_parsed))
    return None


def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    Removes tracking parameters, fragments, etc.
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(url)

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
