"""
Roster sync worker task for syncing Sharks organization players from CapWages.
Runs daily to keep entity database up-to-date with current roster.

Source: https://capwages.com/teams/san_jose_sharks
Includes active roster + non-roster (AHL/prospects).
Excludes dead cap players (traded/bought out, on other teams).
"""
import re
import httpx
from typing import List, Optional
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery
from app.core.database import SessionLocal
from app.core.db_utils import get_or_create_entity
from app.core.config import settings


CAPWAGES_URL = "https://capwages.com/teams/san_jose_sharks"


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
        print("Starting Sharks roster sync from CapWages...")

        # Fetch and parse roster from CapWages
        players = fetch_capwages_roster()

        if players is None:
            print("  ✗ Failed to fetch roster from CapWages")
            return {"status": "error", "message": "Failed to fetch roster"}

        # Process players and collect slugs
        current_roster_slugs = process_players(db, players)

        # Remove player entities no longer in the organization
        removed = remove_departed_players(db, current_roster_slugs)

        db.commit()

        print(f"  ✓ Roster sync complete:")
        print(f"    Players synced: {len(current_roster_slugs)}")
        print(f"    Removed: {removed}")

        return {
            "status": "success",
            "stats": {
                "total": len(current_roster_slugs),
                "removed": removed
            }
        }

    except Exception as exc:
        print(f"  ✗ Error syncing roster: {exc}")
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
            print("  ✗ Could not find expected section markers in CapWages HTML")
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

        print(f"  Found {len(active_players)} active + {len(non_roster_players)} non-roster + {len(reserve_players)} reserve players")
        return players

    except Exception as e:
        print(f"  Error fetching CapWages roster: {e}")
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
    if "," not in raw_name:
        return raw_name if raw_name else None

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
            print(f"    ✓ {name}")

        except Exception as e:
            print(f"    ✗ Error processing {name}: {e}")
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
    from app.models import Entity, ClusterEntity

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
            print(f"    ✗ Removed departed player: {entity.name}")
            removed += 1

    return removed
