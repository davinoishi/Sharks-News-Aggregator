"""
Submission worker tasks for processing user-submitted links.
Handles URL validation, content fetch, and candidate source proposals.
"""
from typing import Optional
from urllib.parse import urlparse
import httpx
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery
from app.core.database import SessionLocal
from app.core.config import settings


@celery.task(name="app.tasks.submissions.process_submission", bind=True)
def process_submission(self, submission_id: int):
    """
    Process a user-submitted link.

    Steps:
    1. Normalize and validate URL
    2. Fetch metadata
    3. Create raw_item
    4. Trigger enrichment
    5. Propose candidate source if domain is new

    Args:
        submission_id: ID of the submission to process
    """
    from app.models import Submission, RawItem, StoryVariant, SubmissionStatus

    db = SessionLocal()
    try:
        # Load submission from database
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            return {"error": "Submission not found", "submission_id": submission_id}

        print(f"Processing submission {submission_id}: {submission.url}")

        # Step 1: Normalize URL
        normalized_url = normalize_url(submission.url)
        domain = extract_domain(normalized_url)

        # Step 2: Check for duplicates
        existing_variant = db.query(StoryVariant).filter(
            StoryVariant.url == normalized_url
        ).first()

        if existing_variant:
            submission.status = SubmissionStatus.DUPLICATE
            submission.story_variant_id = existing_variant.id
            submission.cluster_id = existing_variant.cluster_id
            db.commit()
            print(f"  Duplicate found: variant {existing_variant.id}")
            return {"status": "duplicate", "variant_id": existing_variant.id}

        # Step 3: Fetch metadata
        try:
            metadata = fetch_url_metadata(normalized_url)
        except Exception as e:
            submission.status = SubmissionStatus.REJECTED
            submission.rejection_reason = f"Failed to fetch URL: {str(e)}"
            db.commit()
            print(f"  ✗ Failed to fetch URL: {e}")
            return {"status": "rejected", "reason": str(e)}

        # Step 4: Create raw_item
        from app.tasks.ingest import create_raw_item

        # Use a synthetic source_id = 0 for user submissions (or create a special "User Submissions" source)
        raw_item = create_raw_item(
            db=db,
            source_id=0,  # Special ID for user submissions
            original_url=submission.url,
            raw_title=metadata.get('title'),
            raw_description=metadata.get('description'),
            source_item_id=None,
            published_at=None,
        )

        if not raw_item:
            submission.status = SubmissionStatus.DUPLICATE
            db.commit()
            print(f"  Duplicate found during raw_item creation")
            return {"status": "duplicate"}

        # Step 5: Trigger enrichment
        from app.tasks.enrich import enrich_raw_item
        enrich_raw_item.delay(raw_item.id)

        # Step 6: Check if domain is new, create candidate source
        if not is_known_source(db, domain):
            create_candidate_source.delay(domain, submission_id)

        # Step 7: Update submission status
        submission.status = SubmissionStatus.PUBLISHED
        submission.raw_item_id = raw_item.id
        db.commit()

        print(f"  ✓ Created raw_item {raw_item.id}, queued for enrichment")

        return {
            "status": "success",
            "submission_id": submission_id,
            "raw_item_id": raw_item.id,
            "candidate_source_created": not is_known_source(db, domain)
        }

    except Exception as exc:
        # Mark submission as failed
        submission.status = SubmissionStatus.REJECTED
        submission.rejection_reason = str(exc)
        db.commit()
        print(f"  ✗ Error: {exc}")
        raise
    finally:
        db.close()


@celery.task(name="app.tasks.submissions.create_candidate_source")
def create_candidate_source(domain: str, submission_id: int):
    """
    Create or update candidate_source for a new domain.
    Attempts RSS discovery and queues for review.

    Args:
        domain: Domain name (e.g., example.com)
        submission_id: Original submission ID that discovered this source
    """
    from app.models import CandidateSource, CandidateSourceStatus

    db = SessionLocal()
    try:
        # Check if candidate already exists
        existing = db.query(CandidateSource).filter(CandidateSource.domain == domain).first()
        if existing:
            # Increment counter
            existing.times_submitted = (existing.times_submitted or 1) + 1
            db.commit()
            print(f"Candidate source already exists for {domain}, incremented counter to {existing.times_submitted}")
            return {"status": "already_exists", "candidate_id": existing.id}

        # Attempt RSS discovery
        feed_url = discover_rss_feed(f"https://{domain}")

        # Create candidate source
        candidate = CandidateSource(
            domain=domain,
            base_url=f"https://{domain}",
            discovered_from_submission_id=submission_id,
            discovered_feed_url=feed_url,
            rss_discovery_attempted=True,
            rss_discovery_success=feed_url is not None,
            times_submitted=1,
            status=CandidateSourceStatus.QUEUED_FOR_REVIEW,
        )

        db.add(candidate)
        db.commit()

        print(f"Created candidate source for {domain} (RSS: {'found' if feed_url else 'not found'})")

        # TODO: Send notification for review (email, webhook, etc.)

        return {
            "status": "success",
            "domain": domain,
            "candidate_id": candidate.id,
            "feed_url": feed_url
        }

    finally:
        db.close()


def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    Same implementation as in ingest.py
    """
    from app.tasks.ingest import normalize_url as ingest_normalize_url
    return ingest_normalize_url(url)


def extract_domain(url: str) -> str:
    """
    Extract domain from URL.

    Args:
        url: Full URL

    Returns:
        Domain (e.g., example.com)
    """
    parsed = urlparse(url)
    return parsed.netloc


def fetch_url_metadata(url: str) -> dict:
    """
    Fetch metadata from URL (title, description, etc.).
    Uses trafilatura for article extraction.

    Args:
        url: URL to fetch

    Returns:
        Dict with metadata
    """
    try:
        import trafilatura

        response = httpx.get(url, timeout=settings.request_timeout_seconds, follow_redirects=True)
        response.raise_for_status()

        # Extract article content
        extracted = trafilatura.extract(
            response.text,
            output_format='json',
            include_comments=False,
            include_tables=False,
        )

        if extracted:
            import json
            data = json.loads(extracted)
            return {
                'title': data.get('title'),
                'description': data.get('description'),
                'text': data.get('text'),
                'author': data.get('author'),
                'published': data.get('date'),
                'canonical_url': response.url.str(),
            }

        return {'canonical_url': str(response.url)}

    except Exception as e:
        raise Exception(f"Failed to fetch URL metadata: {str(e)}")


def is_known_source(db: Session, domain: str) -> bool:
    """
    Check if a domain is already an approved source.

    Args:
        db: Database session
        domain: Domain to check

    Returns:
        True if domain is a known source
    """
    from app.models import Source
    from urllib.parse import urlparse

    # Check if any source has this domain
    sources = db.query(Source).all()
    for source in sources:
        # Parse the base_url or feed_url to get domain
        if source.base_url:
            source_domain = urlparse(source.base_url).netloc
            if source_domain == domain:
                return True
        if source.feed_url:
            source_domain = urlparse(source.feed_url).netloc
            if source_domain == domain:
                return True

    return False


def discover_rss_feed(base_url: str) -> Optional[str]:
    """
    Attempt to discover RSS feed for a website.

    Strategies:
    1. Check <link> tags in HTML
    2. Try common RSS paths (/feed, /rss, /feed.xml, etc.)

    Args:
        base_url: Base URL of the website

    Returns:
        RSS feed URL if found, None otherwise
    """
    try:
        from bs4 import BeautifulSoup

        # Fetch homepage
        response = httpx.get(base_url, timeout=10, follow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for RSS link tags
        rss_link = soup.find('link', {'type': 'application/rss+xml'})
        if rss_link and rss_link.get('href'):
            # Handle relative URLs
            href = rss_link['href']
            if href.startswith('http'):
                return href
            else:
                from urllib.parse import urljoin
                return urljoin(base_url, href)

        # Try common RSS paths
        common_paths = ['/feed', '/rss', '/feed.xml', '/rss.xml', '/atom.xml', '/feeds/posts/default']
        for path in common_paths:
            try:
                feed_url = f"{base_url.rstrip('/')}{path}"
                feed_response = httpx.get(feed_url, timeout=5, follow_redirects=True)
                if feed_response.status_code == 200:
                    # Verify it's actually a feed
                    import feedparser
                    feed = feedparser.parse(feed_response.text)
                    if not feed.bozo and feed.entries:
                        return feed_url
            except:
                continue

        return None

    except Exception:
        return None
