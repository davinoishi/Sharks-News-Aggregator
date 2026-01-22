"""
Roster sync worker task for syncing Sharks players from NHL API.
Runs daily to keep entity database up-to-date with current roster.
"""
import httpx
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.tasks.celery_app import celery
from app.core.database import SessionLocal
from app.core.db_utils import get_or_create_entity
from app.core.config import settings


NHL_API_BASE = "https://api-web.nhle.com/v1"
SHARKS_TEAM_CODE = "SJS"
CURRENT_SEASON = "20252026"


@celery.task(name="app.tasks.sync_roster.sync_sharks_roster", bind=True)
def sync_sharks_roster(self):
    """
    Sync all Sharks players (NHL, AHL, prospects) from NHL API.

    This task:
    1. Fetches current roster from NHL API
    2. Creates or updates player entities
    3. Marks entities as active/inactive based on roster status

    Runs daily via Celery Beat schedule.
    """
    db = SessionLocal()
    try:
        print("Starting Sharks roster sync...")

        # Fetch roster from NHL API
        roster_data = fetch_nhl_roster()

        if not roster_data:
            print("  ✗ Failed to fetch roster from NHL API")
            return {"status": "error", "message": "Failed to fetch roster"}

        # Process each position group
        stats = {
            'forwards': 0,
            'defensemen': 0,
            'goalies': 0,
            'total': 0,
            'new': 0,
            'updated': 0
        }

        # Process forwards
        if 'forwards' in roster_data:
            stats['forwards'] = process_players(db, roster_data['forwards'], 'forward')

        # Process defensemen
        if 'defensemen' in roster_data:
            stats['defensemen'] = process_players(db, roster_data['defensemen'], 'defenseman')

        # Process goalies
        if 'goalies' in roster_data:
            stats['goalies'] = process_players(db, roster_data['goalies'], 'goalie')

        stats['total'] = stats['forwards'] + stats['defensemen'] + stats['goalies']

        db.commit()

        print(f"  ✓ Roster sync complete:")
        print(f"    Forwards: {stats['forwards']}")
        print(f"    Defensemen: {stats['defensemen']}")
        print(f"    Goalies: {stats['goalies']}")
        print(f"    Total: {stats['total']}")

        return {
            "status": "success",
            "stats": stats
        }

    except Exception as exc:
        print(f"  ✗ Error syncing roster: {exc}")
        db.rollback()
        raise
    finally:
        db.close()


def fetch_nhl_roster() -> Optional[Dict]:
    """
    Fetch Sharks roster from NHL API.

    Returns:
        Dictionary with forwards, defensemen, goalies arrays
    """
    try:
        url = f"{NHL_API_BASE}/roster/{SHARKS_TEAM_CODE}/{CURRENT_SEASON}"

        response = httpx.get(url, timeout=settings.request_timeout_seconds)
        response.raise_for_status()

        return response.json()

    except Exception as e:
        print(f"  Error fetching NHL roster: {e}")
        return None


def process_players(db: Session, players: List[Dict], position_group: str) -> int:
    """
    Process a list of players and create/update entities.

    Args:
        db: Database session
        players: List of player dictionaries from NHL API
        position_group: 'forward', 'defenseman', or 'goalie'

    Returns:
        Number of players processed
    """
    count = 0

    for player in players:
        try:
            # Extract player info
            first_name = player.get('firstName', {}).get('default', '')
            last_name = player.get('lastName', {}).get('default', '')
            full_name = f"{first_name} {last_name}".strip()

            if not full_name:
                continue

            nhl_id = player.get('id')
            sweater_number = player.get('sweaterNumber')
            position = player.get('positionCode', '')

            # Build metadata
            metadata = {
                'status': 'active',
                'position_group': position_group,
                'position': position,
                'nhl_id': nhl_id,
                'sweater_number': sweater_number,
                'shoots_catches': player.get('shootsCatches'),
                'birth_date': player.get('birthDate'),
                'birth_city': player.get('birthCity', {}).get('default'),
                'birth_country': player.get('birthCountry'),
            }

            # Create or update entity
            entity = get_or_create_entity(
                db,
                name=full_name,
                entity_type='player',
                extra_metadata=metadata
            )

            print(f"    ✓ {full_name} #{sweater_number} ({position})")
            count += 1

        except Exception as e:
            print(f"    ✗ Error processing player: {e}")
            continue

    return count


@celery.task(name="app.tasks.sync_roster.sync_barracuda_roster", bind=True)
def sync_barracuda_roster(self):
    """
    Sync San Jose Barracuda (AHL affiliate) roster.

    Note: NHL API doesn't provide AHL rosters directly.
    This is a placeholder for future implementation using another data source.
    """
    print("Barracuda roster sync not yet implemented")
    print("  Consider using AHL.com or manual updates")

    return {"status": "not_implemented"}


@celery.task(name="app.tasks.sync_roster.mark_inactive_players", bind=True)
def mark_inactive_players(self):
    """
    Mark players as inactive if they haven't been seen in recent roster syncs.

    This task runs after roster sync to update player statuses.
    For now, this is a placeholder - we keep all historical players active
    so they can be detected in news about trades, signings, etc.
    """
    # TODO: Implement inactive player marking based on roster sync history
    print("Player status updates not yet implemented")

    return {"status": "not_implemented"}
