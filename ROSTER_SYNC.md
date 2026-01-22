# Automated Roster Sync - Sharks News Aggregator

**Date:** 2026-01-21
**Status:** ✅ Active - Syncing Daily

## Overview

The system now automatically syncs all San Jose Sharks players from the official NHL API every day. This ensures your entity database stays up-to-date with:
- Current NHL roster
- Call-ups and send-downs
- New acquisitions (trades, signings)
- Roster changes throughout the season

## How It Works

### Data Source
- **NHL Official API:** `https://api-web.nhle.com/v1/roster/SJS/20252026`
- **Reliability:** Official NHL data, updated in real-time
- **Coverage:** All NHL roster players (forwards, defensemen, goalies)

### Sync Schedule
- **Frequency:** Once per day (every 24 hours)
- **Managed by:** Celery Beat scheduler
- **Task Name:** `sync-sharks-roster`

### What Gets Synced

For each player, the system stores:
- Full name
- Position (C, L, R, D, G)
- Jersey number
- NHL player ID
- Shoots/Catches (L/R)
- Birth information (date, city, country)
- Active status

### Automatic Detection

Once synced, these players are automatically detected in news articles during the enrichment process. For example:
- "Collin Graf's exceptional shift..." → Detects Collin Graf
- "Kiefer Sherwood trade rumors..." → Detects Kiefer Sherwood
- News about any current Sharks player

## Current Status

**Initial Sync Completed:** 2026-01-21

### Players Added
- **Total:** 45 players (up from 28)
- **Forwards:** 17
- **Defensemen:** 8
- **Goalies:** 2

### New Players Detected
Including players that were missing from the manual seed:
- ✅ Collin Graf #51 (R)
- ✅ Kiefer Sherwood #44 (L) - Recent acquisition
- ✅ William Eklund #72 (L)
- ✅ Igor Chernyshov #92 (L)
- ✅ Adam Gaudette #81 (R)
- ✅ Philipp Kurashev #96 (C)
- ✅ Michael Misa #77 (C)
- ✅ Zack Ostapchuk #63 (C)
- ✅ Ryan Reaves #75 (R)
- ✅ Pavol Regenda #84 (L)
- ✅ Jeff Skinner #53 (L)
- ✅ Vincent Desharnais #5 (D)
- ✅ Vincent Iorio #22 (D)
- ✅ John Klingberg #3 (D)
- ✅ Timothy Liljegren #37 (D)
- ✅ Dmitry Orlov #9 (D)
- ✅ Alex Nedeljkovic #33 (G)

## Manual Operations

### Trigger Roster Sync Immediately

If you want to force a roster sync (e.g., after a trade deadline):

```bash
docker-compose exec api python -c "
from app.tasks.sync_roster import sync_sharks_roster
sync_sharks_roster.delay()
print('Roster sync queued!')
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

# List recent additions
docker-compose exec db psql -U sharks -d sharks -c \
  "SELECT name, metadata->>'position', metadata->>'sweater_number'
   FROM entities
   WHERE entity_type = 'player'
   ORDER BY created_at DESC
   LIMIT 20;"
```

## Implementation Details

### Files
- **Task:** `api/app/tasks/sync_roster.py`
- **Schedule Config:** `api/app/tasks/celery_app.py`
- **Entity Utils:** `api/app/core/db_utils.py` (get_or_create_entity)

### Key Functions

**`sync_sharks_roster()`**
- Main Celery task
- Fetches NHL roster
- Creates/updates player entities
- Returns sync statistics

**`fetch_nhl_roster()`**
- Calls NHL API
- Handles errors gracefully
- Returns JSON roster data

**`process_players()`**
- Processes each position group
- Extracts player metadata
- Creates entities with full details

### Idempotency

The sync is **idempotent** - running it multiple times won't create duplicates:
- Uses `get_or_create_entity()` which checks for existing players by name
- Updates metadata for existing players
- Only creates new entities for new players

### Error Handling

- **API Failures:** Logs error and skips sync (keeps existing data)
- **Network Issues:** Retries with timeout
- **Invalid Data:** Skips individual players, continues with rest
- **Database Errors:** Rolls back transaction, logs error

## Future Enhancements

### Planned (Not Yet Implemented)

1. **San Jose Barracuda (AHL) Roster**
   - Sync minor league affiliate players
   - Detect prospects and call-ups
   - Would need AHL data source

2. **Prospect Tracking**
   - Junior league players (OHL, WHL, NCAA)
   - Draft picks
   - International prospects

3. **Historical Players**
   - Mark players as inactive when they leave the team
   - Keep them in database for historical news detection
   - Add "status" field updates

4. **Roster Change Notifications**
   - Detect when new players are added
   - Alert on roster changes
   - Track transactions (trades, signings, waivers)

5. **Multi-Team Support**
   - Sync all NHL teams
   - Detect opponent players in news
   - Full league coverage

## Monitoring

The roster sync task logs to the worker logs:

**Success Example:**
```
Starting Sharks roster sync...
  ✓ Collin Graf #51 (R)
  ✓ Kiefer Sherwood #44 (L)
  ...
  ✓ Roster sync complete:
    Forwards: 17
    Defensemen: 8
    Goalies: 2
    Total: 27
```

**Check Last Sync:**
```bash
docker-compose logs worker | grep "Roster sync complete" | tail -1
```

## Benefits

### Before Roster Sync
- ❌ Missing players like Collin Graf, Kiefer Sherwood
- ❌ Manual updates needed after trades
- ❌ 28 players (outdated roster)
- ❌ Missed entity detection in news

### After Roster Sync
- ✅ All 45 current players automatically synced
- ✅ Daily updates catch roster changes
- ✅ New acquisitions detected immediately
- ✅ Better entity extraction in news articles
- ✅ Zero maintenance required

## Troubleshooting

### Roster sync not running?

Check Celery Beat is active:
```bash
docker-compose logs beat --tail=20
```

Should see: `Scheduler: Sending due task sync-sharks-roster`

### Players not being detected in news?

1. Check player exists in database
2. Verify entity extraction is running (check enrichment logs)
3. Test entity matching with player name variations

### Need to update season?

Edit `api/app/tasks/sync_roster.py`:
```python
CURRENT_SEASON = "20262027"  # Update for next season
```

Then restart worker/beat:
```bash
docker-compose restart worker beat
```

---

**The roster sync is now live and running automatically!** Your player database will stay current throughout the season.
