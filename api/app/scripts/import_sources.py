#!/usr/bin/env python3
"""
Import initial sources from CSV file into the database.

Usage:
    python -m app.scripts.import_sources /path/to/initial_sources.csv

Or from Docker:
    docker-compose exec api python -m app.scripts.import_sources /app/../initial_sources.csv
"""
import sys
import csv
from pathlib import Path
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models import Source, SourceCategory, SourceStatus, IngestMethod


def parse_ingest_method(method_str: str) -> IngestMethod:
    """
    Parse ingest method from CSV string.

    Args:
        method_str: Method string from CSV (rss, html, twitter, reddit)

    Returns:
        IngestMethod enum value
    """
    method_map = {
        'rss': IngestMethod.RSS,
        'html': IngestMethod.HTML,
        'twitter': IngestMethod.TWITTER,
        'reddit': IngestMethod.REDDIT,
        'api': IngestMethod.API,
    }

    method_lower = method_str.lower().strip()
    if method_lower not in method_map:
        print(f"Warning: Unknown ingest method '{method_str}', defaulting to RSS")
        return IngestMethod.RSS

    return method_map[method_lower]


def parse_category(category_str: str) -> SourceCategory:
    """
    Parse source category from CSV string.

    Args:
        category_str: Category string from CSV (official, press, other)

    Returns:
        SourceCategory enum value
    """
    category_map = {
        'official': SourceCategory.OFFICIAL,
        'press': SourceCategory.PRESS,
        'other': SourceCategory.OTHER,
    }

    category_lower = category_str.lower().strip()
    if category_lower not in category_map:
        print(f"Warning: Unknown category '{category_str}', defaulting to OTHER")
        return SourceCategory.OTHER

    return category_map[category_lower]


def parse_tier(tier_str: str) -> int:
    """
    Parse tier into priority number.
    Lower tier = higher priority (lower number).

    Args:
        tier_str: Tier string from CSV (1, 2, 3)

    Returns:
        Priority integer (tier 1 = priority 10, tier 2 = priority 50, tier 3 = priority 100)
    """
    try:
        tier = int(tier_str)
        # Map tier to priority: tier 1 = 10, tier 2 = 50, tier 3 = 100
        priority_map = {1: 10, 2: 50, 3: 100}
        return priority_map.get(tier, 100)
    except (ValueError, TypeError):
        return 100


def import_sources_from_csv(csv_path: str, dry_run: bool = False) -> int:
    """
    Import sources from CSV file into database.

    Args:
        csv_path: Path to CSV file
        dry_run: If True, print what would be imported without saving

    Returns:
        Number of sources imported
    """
    csv_file = Path(csv_path)

    if not csv_file.exists():
        print(f"Error: CSV file not found at {csv_path}")
        return 0

    db = SessionLocal()
    imported_count = 0
    skipped_count = 0

    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            print(f"Reading sources from {csv_path}...")
            print(f"Dry run: {dry_run}\n")

            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                name = row.get('name', '').strip()
                url = row.get('url', '').strip()
                category = row.get('category', 'other').strip()
                tier = row.get('tier', '3').strip()
                ingest_method = row.get('ingest_method', 'rss').strip()
                feed_url = row.get('feed_url', '').strip()
                notes = row.get('notes', '').strip()

                # Validate required fields
                if not name or not url:
                    print(f"Row {row_num}: Skipping - missing name or URL")
                    skipped_count += 1
                    continue

                # Check if source already exists
                existing = db.query(Source).filter(Source.name == name).first()
                if existing:
                    print(f"Row {row_num}: Skipping '{name}' - already exists (ID: {existing.id})")
                    skipped_count += 1
                    continue

                # Parse enums
                category_enum = parse_category(category)
                method_enum = parse_ingest_method(ingest_method)
                priority = parse_tier(tier)

                # Build metadata
                extra_metadata = {}
                if notes:
                    extra_metadata['notes'] = notes

                # Create source object
                source = Source(
                    name=name,
                    category=category_enum,
                    ingest_method=method_enum,
                    base_url=url,
                    feed_url=feed_url if feed_url else None,
                    status=SourceStatus.APPROVED,
                    priority=priority,
                    extra_metadata=extra_metadata,
                )

                if dry_run:
                    print(f"Row {row_num}: Would import '{name}'")
                    print(f"  Category: {category_enum.value}, Method: {method_enum.value}, Priority: {priority}")
                    print(f"  URL: {url}")
                    if feed_url:
                        print(f"  Feed: {feed_url}")
                    print()
                else:
                    try:
                        db.add(source)
                        db.flush()  # Get the ID
                        print(f"Row {row_num}: ✓ Imported '{name}' (ID: {source.id})")
                        imported_count += 1
                    except IntegrityError as e:
                        db.rollback()
                        print(f"Row {row_num}: Error importing '{name}': {e}")
                        skipped_count += 1

        if not dry_run:
            db.commit()
            print(f"\n✓ Successfully imported {imported_count} sources")
        else:
            print(f"\nDry run complete. Would import {imported_count} sources")

        if skipped_count > 0:
            print(f"⚠ Skipped {skipped_count} sources")

        return imported_count

    except Exception as e:
        db.rollback()
        print(f"\n✗ Error during import: {e}")
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m app.scripts.import_sources <csv_file> [--dry-run]")
        print("\nExample:")
        print("  python -m app.scripts.import_sources initial_sources.csv")
        print("  python -m app.scripts.import_sources initial_sources.csv --dry-run")
        sys.exit(1)

    csv_path = sys.argv[1]
    dry_run = '--dry-run' in sys.argv

    try:
        count = import_sources_from_csv(csv_path, dry_run=dry_run)

        if not dry_run and count > 0:
            print("\n" + "="*60)
            print("Next steps:")
            print("  1. Verify sources in database:")
            print("     docker-compose exec db psql -U sharks -d sharks -c 'SELECT id, name, category, status FROM sources;'")
            print("  2. Start ingestion workers:")
            print("     docker-compose restart worker beat")
            print("="*60)

    except Exception as e:
        print(f"\n✗ Failed to import sources: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
