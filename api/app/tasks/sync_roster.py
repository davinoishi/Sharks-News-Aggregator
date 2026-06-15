"""
Roster sync worker task for syncing Sharks organization players from CapWages.
Runs daily to keep entity database up-to-date with current roster.

Source: https://capwages.com/teams/san_jose_sharks
Includes active roster + non-roster (AHL/prospects).
Excludes dead cap players (traded/bought out, on other teams).
"""
import logging
import re
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.alerts import send_alert
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.db_utils import get_or_create_entity, get_site_metric, set_site_metric
from app.tasks.celery_app import celery

logger = logging.getLogger(__name__)

CAPWAGES_URL = "https://capwages.com/teams/san_jose_sharks"

# Sanity bounds for a parsed roster (R2-F2). A healthy CapWages parse returns
# ~40-90 names (active roster + AHL/prospects + reserve picks). The scrape keys
# off literal HTML markers, so a site redesign or partial parse can silently
# yield a tiny/empty list — and remove_departed_players would then delete every
# real player entity. These bounds + the shrink guard make the sync refuse to
# act on an implausible roster instead.
MIN_EXPECTED_ROSTER = 20
MAX_EXPECTED_ROSTER = 120
# Reject a roster that shrank by more than this fraction vs the last good sync.
MAX_ROSTER_SHRINK_FRACTION = 0.30
# SiteMetrics key holding the last successful roster size (shrink-guard baseline).
METRIC_LAST_ROSTER_COUNT = "roster_sync_last_count"


def validate_roster_size(count: int, prev_count: int) -> tuple:
    """Decide whether a parsed roster of ``count`` players is plausible.

    ``prev_count`` is the size of the last successful sync (0 if none). Returns
    ``(ok: bool, reason: str)``. A rejected roster must not drive entity removal.
    """
    if count < MIN_EXPECTED_ROSTER:
        return False, f"roster too small ({count} < {MIN_EXPECTED_ROSTER}); parse likely broken"
    if count > MAX_EXPECTED_ROSTER:
        return False, f"roster too large ({count} > {MAX_EXPECTED_ROSTER}); parse likely broken"
    if prev_count and count < prev_count * (1 - MAX_ROSTER_SHRINK_FRACTION):
        return False, (
            f"roster shrank sharply ({prev_count} -> {count}, "
            f">{int(MAX_ROSTER_SHRINK_FRACTION * 100)}%); treating as suspect"
        )
    return True, "ok"


@celery.task(name="app.tasks.sync_roster.sync_sharks_roster", bind=True)
def sync_sharks_roster(self):
    """
    Sync all Sharks players (NHL + AHL/prospects) from CapWages.

    This task:
    1. Scrapes the CapWages team page for active roster + non-roster players
    2. Creates or updates player entities
    3. Removes entities for players no longer in the organization

    Runs daily via Celery Beat schedule.
    """
    db = SessionLocal()
    try:
        logger.info("Starting Sharks roster sync from CapWages...")

        # Fetch and parse roster from CapWages
        players = fetch_capwages_roster()

        if players is None:
            # fetch already logged the cause (missing markers / HTTP error).
            send_alert("Sharks roster sync: failed to fetch/parse CapWages roster")
            return {"status": "error", "message": "Failed to fetch roster"}

        # Guard against a structurally-valid page that parsed into an implausible
        # roster: acting on it would let remove_departed_players wipe real
        # players. Abort BEFORE any destructive step and alert (R2-F2).
        prev_count = get_site_metric(db, METRIC_LAST_ROSTER_COUNT, 0)
        ok, reason = validate_roster_size(len(players), prev_count)
        if not ok:
            send_alert(
                f"Sharks roster sync aborted: {reason}",
                parsed_count=len(players),
                previous_count=prev_count,
            )
            return {
                "status": "aborted",
                "reason": reason,
                "parsed_count": len(players),
                "previous_count": prev_count,
            }

        # Process players and collect slugs
        current_roster_slugs = process_players(db, players)

        # Remove player entities no longer in the organization
        removed = remove_departed_players(db, current_roster_slugs)

        # Record this roster size as the new shrink-guard baseline (commits).
        set_site_metric(db, METRIC_LAST_ROSTER_COUNT, len(current_roster_slugs))
        db.commit()

        logger.info(
            "  ✓ Roster sync complete: %d players synced, %d removed",
            len(current_roster_slugs), removed,
        )

        return {
            "status": "success",
            "stats": {
                "total": len(current_roster_slugs),
                "removed": removed
            }
        }

    except Exception as exc:
        logger.exception("  ✗ Error syncing roster: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()


def fetch_capwages_roster() -> Optional[List[str]]:
    """
    Fetch Sharks organization players from CapWages.

    Parses the HTML to extract player names from the Active Roster
    and Non-Roster sections, skipping Dead Cap players (traded/bought out).

    Returns:
        List of player full names ("FirstName LastName"), or None on error.
    """
    try:
        response = httpx.get(
            CAPWAGES_URL,
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": "SharksNewsAggregator/1.0"},
        )
        response.raise_for_status()
        html = response.text

        # Find section boundaries
        dead_cap_pos = html.find(">dead cap<")
        non_roster_pos = html.find(">non-roster<")

        if dead_cap_pos == -1 or non_roster_pos == -1:
            logger.error("  ✗ Could not find expected section markers in CapWages HTML")
            return None

        # Extract player links: <a href="/players/slug">LastName, FirstName</a>
        player_link_pattern = re.compile(
            r'<a[^>]*href="/players/[^"]*"[^>]*>([^<]+)</a>'
        )

        # Reserve list uses spans: <span value="LastName, FirstName">
        reserve_span_pattern = re.compile(
            r'<span[^>]*value="([^"]+)"[^>]*>'
        )

        # Active roster: before dead cap section
        active_section = html[:dead_cap_pos]
        active_players = player_link_pattern.findall(active_section)

        # Non-roster (AHL/prospects): after non-roster section header
        non_roster_section = html[non_roster_pos:]
        non_roster_players = player_link_pattern.findall(non_roster_section)

        # Reserve list (unsigned draft picks): spans after non-roster section
        reserve_players = reserve_span_pattern.findall(non_roster_section)

        # Convert "LastName, FirstName" to "FirstName LastName" and dedupe
        seen = set()
        players = []
        for raw_name in active_players + non_roster_players + reserve_players:
            name = parse_player_name(raw_name)
            if name and name not in seen:
                seen.add(name)
                players.append(name)

        logger.info(
            "  Found %d active + %d non-roster + %d reserve players",
            len(active_players), len(non_roster_players), len(reserve_players),
        )
        return players

    except Exception as e:
        logger.error("  Error fetching CapWages roster: %s", e)
        return None


def parse_player_name(raw_name: str) -> Optional[str]:
    """
    Convert CapWages name format to standard "FirstName LastName".

    CapWages uses "LastName, FirstName" format.

    Args:
        raw_name: Name string from HTML (e.g., "Celebrini, Macklin")

    Returns:
        Normalized name (e.g., "Macklin Celebrini") or None if unparseable.
    """
    raw_name = raw_name.strip()
    if not raw_name or not re.search(r'[a-zA-Z]', raw_name):
        return None
    if "," not in raw_name:
        return raw_name

    parts = raw_name.split(",", 1)
    last_name = parts[0].strip()
    first_name = parts[1].strip()

    if not first_name or not last_name:
        return None

    return f"{first_name} {last_name}"


def process_players(db: Session, player_names: List[str]) -> set:
    """
    Create or update entity records for a list of player names.

    Args:
        db: Database session
        player_names: List of player full names

    Returns:
        Set of player slugs processed
    """
    from app.models import Entity

    slugs = set()

    for name in player_names:
        try:
            entity = get_or_create_entity(
                db,
                name=name,
                entity_type='player',
                extra_metadata={'status': 'active'}
            )
            slug = Entity.make_slug(name)
            slugs.add(slug)
            logger.debug("    ✓ %s", name)

        except Exception as e:
            logger.warning("    ✗ Error processing %s: %s", name, e)
            continue

    return slugs


def remove_departed_players(db: Session, current_roster_slugs: set) -> int:
    """
    Remove player entities that are no longer in the Sharks organization.

    This prevents false positive matches on articles mentioning
    former Sharks players now on other teams.

    Args:
        db: Database session
        current_roster_slugs: Set of slugs for players currently in org

    Returns:
        Number of entities removed
    """
    from app.models import ClusterEntity, Entity

    all_player_entities = db.query(Entity).filter(
        Entity.entity_type == 'player'
    ).all()

    removed = 0
    for entity in all_player_entities:
        if entity.slug not in current_roster_slugs:
            # Remove cluster associations first
            db.query(ClusterEntity).filter(
                ClusterEntity.entity_id == entity.id
            ).delete()

            db.delete(entity)
            logger.info("    ✗ Removed departed player: %s", entity.name)
            removed += 1

    return removed
