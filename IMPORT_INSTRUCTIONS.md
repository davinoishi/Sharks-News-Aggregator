# How to Import CSV Sources

Quick reference for importing the initial sources from `initial_sources.csv` into the database.

## Prerequisites

Make sure Docker services are running:

```bash
docker-compose up -d
docker-compose ps  # All services should show "Up"
```

## Method 1: Using the Import Script (Recommended)

### Dry Run (Preview)

First, do a dry run to see what will be imported without actually saving to the database:

```bash
docker-compose exec api python -m app.scripts.import_sources /app/../initial_sources.csv --dry-run
```

You'll see output like:

```
Reading sources from initial_sources.csv...
Dry run: True

Row 2: Would import 'NHL.com - San Jose Sharks'
  Category: official, Method: rss, Priority: 10
  URL: https://www.nhl.com/sharks/
  Feed: https://www.nhl.com/sharks/news/rss

Row 3: Would import 'San Jose Sharks PR'
  Category: official, Method: twitter, Priority: 10
  URL: https://x.com/SanJoseSharksPR

...

Dry run complete. Would import 15 sources
```

### Actual Import

If the preview looks good, run it for real:

```bash
docker-compose exec api python -m app.scripts.import_sources /app/../initial_sources.csv
```

Expected output:

```
Reading sources from initial_sources.csv...
Dry run: False

Row 2: ✓ Imported 'NHL.com - San Jose Sharks' (ID: 1)
Row 3: ✓ Imported 'San Jose Sharks PR' (ID: 2)
Row 4: ✓ Imported 'San Jose Hockey Now' (ID: 3)
Row 5: ✓ Imported 'The Mercury News - Sharks' (ID: 4)
Row 6: ✓ Imported 'NBC Sports Bay Area - Sharks' (ID: 5)
Row 7: ✓ Imported 'The Hockey Writers - Sharks' (ID: 6)
Row 8: ✓ Imported 'Fear the Fin' (ID: 7)
Row 9: ✓ Imported 'Pro Hockey Rumors' (ID: 8)
Row 10: ✓ Imported 'CBS Sports - Sharks' (ID: 9)
Row 11: ✓ Imported 'FOX Sports - Sharks' (ID: 10)
Row 12: ✓ Imported 'Teal Town USA' (ID: 11)
Row 13: ✓ Imported 'Blades of Teal' (ID: 12)
Row 14: ✓ Imported 'Reddit - r/SanJoseSharks' (ID: 13)
Row 15: ✓ Imported 'Yardbarker - Sharks' (ID: 14)
Row 16: ✓ Imported 'Sharks Audio Network' (ID: 15)

✓ Successfully imported 15 sources

============================================================
Next steps:
  1. Verify sources in database:
     docker-compose exec db psql -U sharks -d sharks -c 'SELECT id, name, category, status FROM sources;'
  2. Start ingestion workers:
     docker-compose restart worker beat
============================================================
```

## Method 2: Direct SQL Import (Alternative)

If you prefer to use SQL directly, you can connect to the database:

```bash
# Connect to PostgreSQL
docker-compose exec db psql -U sharks -d sharks
```

Then manually insert sources:

```sql
INSERT INTO sources (name, category, ingest_method, base_url, feed_url, status, priority)
VALUES (
  'NHL.com - San Jose Sharks',
  'official',
  'rss',
  'https://www.nhl.com/sharks/',
  'https://www.nhl.com/sharks/news/rss',
  'approved',
  10
);
```

But **Method 1 is much easier!**

## Verifying the Import

### Check via Database Management Script

```bash
docker-compose exec api python -m app.scripts.db_manage sources
```

### Check via Direct SQL Query

```bash
docker-compose exec db psql -U sharks -d sharks -c "SELECT id, name, category, status, priority FROM sources ORDER BY priority;"
```

### Check via API

```bash
# Once the API is running
curl http://localhost:8000/health

# Note: There's no direct API endpoint to list sources in the public API yet,
# but you can check the worker logs to see them being used
docker-compose logs worker
```

## Re-importing or Updating Sources

The import script is **idempotent** - it won't create duplicates.

If you run it twice, you'll see:

```
Row 2: Skipping 'NHL.com - San Jose Sharks' - already exists (ID: 1)
Row 3: Skipping 'San Jose Sharks PR' - already exists (ID: 2)
...

✓ Successfully imported 0 sources
⚠ Skipped 15 sources
```

To update a source:

1. Delete from database first (or modify via SQL)
2. Re-run the import script

Or use SQL directly:

```bash
docker-compose exec db psql -U sharks -d sharks
```

```sql
-- Update a source's feed URL
UPDATE sources
SET feed_url = 'https://new-feed-url.com/rss'
WHERE name = 'NHL.com - San Jose Sharks';
```

## Editing the CSV

You can edit `initial_sources.csv` to add/remove/modify sources.

**CSV Format:**

```csv
name,url,category,tier,ingest_method,feed_url,notes
Source Name,https://example.com,official,1,rss,https://example.com/feed,Optional notes
```

**Required columns:**
- `name` - Display name
- `url` - Base website URL
- `category` - `official`, `press`, or `other`
- `tier` - `1` (high priority), `2` (medium), or `3` (low)
- `ingest_method` - `rss`, `html`, `twitter`, `reddit`, or `api`

**Optional columns:**
- `feed_url` - RSS feed URL (required for rss method)
- `notes` - Internal notes

After editing, re-run the import:

```bash
docker-compose exec api python -m app.scripts.import_sources /app/../initial_sources.csv
```

## Troubleshooting

### "File not found" error

The path `/app/../initial_sources.csv` works because:
- `/app` is the working directory inside the container
- `..` goes up one level to the project root
- `initial_sources.csv` is in the project root

If it's not working, you can mount the CSV directly:

```bash
# Copy CSV into the container
docker cp initial_sources.csv $(docker-compose ps -q api):/tmp/sources.csv

# Then import
docker-compose exec api python -m app.scripts.import_sources /tmp/sources.csv
```

### Database connection errors

Make sure the database is running:

```bash
docker-compose ps db
docker-compose logs db
```

Test the connection:

```bash
docker-compose exec api python -c "from app.core.database import SessionLocal; db = SessionLocal(); print('✓ Connected')"
```

### Import script crashes

Check the logs:

```bash
docker-compose logs api
```

Common issues:
- Missing columns in CSV
- Invalid enum values (category, ingest_method)
- Encoding issues (use UTF-8)

## What Happens After Import?

1. **Sources are active** - Status is set to `approved` by default
2. **Workers will use them** - The ingest worker will fetch from these sources every 10 minutes (configured by `INGEST_INTERVAL_MINUTES`)
3. **Check worker logs** - Wait 10 minutes and check: `docker-compose logs -f worker`

You should see logs like:

```
[2026-01-21 14:30:00] INFO: Fetching from NHL.com - San Jose Sharks (ID: 1)
[2026-01-21 14:30:02] INFO: Found 10 new items from NHL.com - San Jose Sharks
...
```

## Next Step: Seed Entities

After importing sources, seed the entities (players/coaches):

```bash
docker-compose exec api python -m app.scripts.seed_entities
```

See `SETUP_GUIDE.md` for complete setup instructions.
