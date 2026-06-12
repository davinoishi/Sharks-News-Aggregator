# Documentation

Project docs for the Sharks News Aggregator. Start with the root
[README](../README.md) for a quick overview; the files here go deeper.

## Guides

| Doc | What it covers |
|-----|----------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Tech stack, the 7 containers, data flow, file structure, security |
| [SETUP_GUIDE.md](SETUP_GUIDE.md) | End-to-end local + Pi setup walkthrough |
| [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) | What's hardened/configured for production |
| [IMPORT_SOURCES.md](IMPORT_SOURCES.md) | Importing news sources from `initial_sources.csv` |
| [ROSTER_SYNC.md](ROSTER_SYNC.md) | Daily player-roster sync from CapWages |

## Reference

| Doc | What it covers |
|-----|----------------|
| [MODELS.md](MODELS.md) | SQLAlchemy models, query builders, enums |
| [MIGRATIONS.md](MIGRATIONS.md) | Alembic database migrations |
| [BACKUP_RESTORE.md](BACKUP_RESTORE.md) | Nightly Postgres backups + restore procedure |

## Project history

| Doc | What it covers |
|-----|----------------|
| [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md) | The 2026-06 codebase review and 9-brief improvement plan (all merged) |
| [briefs/](briefs/) | The individual execution briefs (historical record) |
