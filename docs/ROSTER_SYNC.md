# Automated Roster Sync - Sharks News Aggregator

The system syncs the full San Jose Sharks organization (~77 players: NHL roster
+ AHL/Barracuda + unsigned reserves) from CapWages once per day.

## Overview

The system automatically syncs all San Jose Sharks organization players from CapWages every day. This ensures the entity database stays up-to-date with the full organization:
- Active NHL roster
- Non-roster players (AHL / San Jose Barracuda)
- Reserve list (unsigned draft picks)

Players who leave the organization (traded, bought out, waived) are automatically removed to prevent false positive matches in news articles.

## How It Works

### Data Source
- **CapWages:** `https://capwages.com/teams/san_jose_sharks`
- **Coverage:** Full organization (NHL + AHL + unsigned reserves)
- **Sections parsed:**
  - Active Roster (before "dead cap" section)
  - Non-Roster / Minors (after "non-roster" section header)
  - Reserve List (unsigned draft picks, via span elements)
- **Excluded:** Dead Cap players (traded/bought out, on other teams)

### Sync Schedule
- **Frequency:** Once per day (every 24 hours)
- **Managed by:** Celery Beat scheduler
- **Task Name:** `sync-sharks-roster`

### What Gets Synced

For each player, the system stores:
- Full name (converted from "LastName, FirstName" to "FirstName LastName")
- Entity slug (URL-friendly identifier for matching)
- Entity type: `player`
- Active status metadata

### Departed Player Removal

After syncing the current roster, the task:
1. Compares all existing player entities against the current CapWages roster
2. Removes any player entity whose slug is NOT in the current roster
3. Cleans up associated `cluster_entity` records

This prevents articles about former Sharks players (now on other teams) from triggering false positive entity matches in the relevance/clustering system.

### Automatic Detection

Once synced, these players are automatically detected in news articles during the enrichment process. For example:
- "Macklin Celebrini scores twice..." -> Detects Macklin Celebrini
- "Sharks reassign Igor Chernyshov..." -> Detects Igor Chernyshov
- "Joshua Ravensbergen signs ELC..." -> Detects Joshua Ravensbergen

## Typical Sync Size

A full sync covers roughly:
- **Active Roster:** ~28 players
- **Non-Roster (AHL/Prospects):** ~23 players
- **Reserve List (Unsigned):** ~26 players
- **Total:** ~77 players

(Exact counts shift as the roster changes.)

## Manual Operations

### Trigger Roster Sync Immediately

If you want to force a roster sync (e.g., after a trade deadline):

```bash
docker-compose exec api python -c "
from app.tasks.sync_roster import sync_sharks_roster
result = sync_sharks_roster()
print(result)
"
```

### Check Sync Logs

```bash
# View the most recent roster sync
docker-compose logs worker --tail=100 | grep -A30 "Starting Sharks roster"
```

### Verify Players in Database

```bash
# Count total players
docker-compose exec db psql -U sharks -d sharks -c \
  "SELECT COUNT(*) FROM entities WHERE entity_type = 'player';"

# List all players
docker-compose exec db psql -U sharks -d sharks -c \
  "SELECT name, slug FROM entities WHERE entity_type = 'player' ORDER BY name;"
```

## Implementation Details

### Files
- **Task:** `api/app/tasks/sync_roster.py`
- **Schedule Config:** `api/app/tasks/celery_app.py`
- **Entity Utils:** `api/app/core/db_utils.py` (get_or_create_entity)

### Key Functions

**`sync_sharks_roster()`**
- Main Celery task
- Fetches roster from CapWages
- Creates/updates player entities
- Removes departed players
- Returns sync statistics

**`fetch_capwages_roster()`**
- Fetches CapWages team page via HTTP
- Parses HTML to extract player names from Active Roster, Non-Roster, and Reserve List sections
- Skips Dead Cap section (players on other teams)
- Converts "LastName, FirstName" format to "FirstName LastName"
- Returns deduplicated list of player names

**`remove_departed_players()`**
- Finds all player entities not in current roster slugs
- Removes their cluster_entity associations
- Deletes the entity records
- Returns count of removed players

### Idempotency

The sync is **idempotent** - running it multiple times won't create duplicates:
- Uses `get_or_create_entity()` which checks for existing players by slug
- Updates metadata for existing players
- Only creates new entities for new players
- Only removes entities not in current roster

### Error Handling

- **HTTP Failures:** Logs error and skips sync (keeps existing data); fires an alert
- **HTML Structure Changes:** Returns None if section markers not found; fires an alert
- **Individual Player Errors:** Skips player, continues with rest
- **Database Errors:** Rolls back transaction, logs error

### Roster validation guard (R2-F2)

Because `remove_departed_players()` deletes every player entity not in the parsed
roster, a partial or broken parse could silently wipe the roster. Before any
destructive step the sync validates the parsed size and **aborts without
deleting** (returning `status: "aborted"` and firing an alert) when:

- the roster is **below `MIN_EXPECTED_ROSTER`** (20) or **above
  `MAX_EXPECTED_ROSTER`** (120) — the parse is implausible; or
- it **shrank by more than `MAX_ROSTER_SHRINK_FRACTION`** (30%) versus the last
  successful sync (tracked in `site_metrics` under `roster_sync_last_count`).

Alerts go to `ALERT_WEBHOOK_URL` when configured (always logged at `ERROR`
regardless), so a CapWages redesign surfaces immediately instead of quietly
draining the entity table. A successful sync records its size as the new
baseline.

## HTML Parsing Details

The CapWages page structure:

```
[Active Roster]          <- Player links: <a href="/players/slug">LastName, FirstName</a>
  ... players ...

[Dead Cap]               <- SKIPPED (traded/bought out players)
  ... players ...

[Non-Roster]             <- Player links: <a href="/players/slug">LastName, FirstName</a>
  ... players ...

[Reserve List]           <- Span elements: <span value="LastName, FirstName">
  ... players ...
```

Section boundaries are identified by text markers:
- `>dead cap<` - Start of dead cap section
- `>non-roster<` - Start of non-roster section

## Monitoring

The roster sync task logs to the worker logs:

**Success Example** (per-player lines are at `DEBUG`; `LOG_LEVEL=INFO` shows the summary):
```
... INFO  app.tasks.sync_roster: Starting Sharks roster sync from CapWages...
... INFO  app.tasks.sync_roster:   Found 28 active + 23 non-roster + 26 reserve players
... INFO  app.tasks.sync_roster:     ✗ Removed departed player: Mikael Granlund
... INFO  app.tasks.sync_roster:   ✓ Roster sync complete: 77 players synced, 1 removed
```

**Check Last Sync:**
```bash
docker-compose logs worker | grep "Roster sync complete" | tail -1
```

## Troubleshooting

### Roster sync not running?

Check Celery Beat is active:
```bash
docker-compose logs beat --tail=20
```

Should see: `Scheduler: Sending due task sync-sharks-roster`

### CapWages page structure changed?

If the sync fails with "Could not find expected section markers", the CapWages HTML structure may have changed. Check:
1. Verify the page is accessible: `curl -s -o /dev/null -w "%{http_code}" https://capwages.com/teams/san_jose_sharks`
2. Check for the section markers: `>dead cap<` and `>non-roster<`
3. Update the parsing logic in `fetch_capwages_roster()` if needed

### Players not being detected in news?

1. Check player exists in database: `SELECT * FROM entities WHERE name ILIKE '%player_name%';`
2. Verify entity extraction is running (check enrichment logs)
3. Check the relevance filter keywords in `app/enrichment/classify.py`

### False positive matches from former players?

If a departed player is still causing matches:
1. Check if they were removed: `SELECT * FROM entities WHERE name ILIKE '%player_name%';`
2. If still present, trigger a manual roster sync
3. If CapWages still lists them, they may be on a buried contract (still in org)
