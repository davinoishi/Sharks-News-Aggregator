#!/usr/bin/env python3
"""
Database management CLI for common operations.

Usage:
    python -m app.scripts.db_manage <command> [options]

Commands:
    status      - Show database status and counts
    sources     - List all sources
    clusters    - List recent clusters
    tags        - Show tag distribution
    entities    - List entities
    reset       - Reset database (WARNING: deletes all data)
"""
import sys
from datetime import datetime, timedelta
from sqlalchemy import func

from app.core.database import SessionLocal
from app.models import (
    Source, RawItem, StoryVariant, Cluster, Tag, Entity,
    Submission, CandidateSource, ClusterStatus
)


def show_status():
    """Show database status and record counts."""
    db = SessionLocal()
    try:
        print("="*60)
        print("DATABASE STATUS")
        print("="*60)

        # Count records
        source_count = db.query(func.count(Source.id)).scalar()
        raw_item_count = db.query(func.count(RawItem.id)).scalar()
        variant_count = db.query(func.count(StoryVariant.id)).scalar()
        cluster_count = db.query(func.count(Cluster.id)).filter(
            Cluster.status == ClusterStatus.ACTIVE
        ).scalar()
        total_clusters = db.query(func.count(Cluster.id)).scalar()
        tag_count = db.query(func.count(Tag.id)).scalar()
        entity_count = db.query(func.count(Entity.id)).scalar()
        submission_count = db.query(func.count(Submission.id)).scalar()
        candidate_count = db.query(func.count(CandidateSource.id)).scalar()

        print(f"\nRecord Counts:")
        print(f"  Sources:           {source_count}")
        print(f"  Raw Items:         {raw_item_count}")
        print(f"  Story Variants:    {variant_count}")
        print(f"  Active Clusters:   {cluster_count} (total: {total_clusters})")
        print(f"  Tags:              {tag_count}")
        print(f"  Entities:          {entity_count}")
        print(f"  Submissions:       {submission_count}")
        print(f"  Candidate Sources: {candidate_count}")

        # Recent activity
        print(f"\nRecent Activity (last 24 hours):")
        yesterday = datetime.utcnow() - timedelta(days=1)

        recent_items = db.query(func.count(RawItem.id)).filter(
            RawItem.created_at >= yesterday
        ).scalar()

        recent_clusters = db.query(func.count(Cluster.id)).filter(
            Cluster.last_seen_at >= yesterday
        ).scalar()

        print(f"  New raw items:     {recent_items}")
        print(f"  Updated clusters:  {recent_clusters}")

        print("="*60)

    finally:
        db.close()


def list_sources():
    """List all sources."""
    db = SessionLocal()
    try:
        sources = db.query(Source).order_by(Source.priority.asc()).all()

        print("="*60)
        print(f"SOURCES ({len(sources)} total)")
        print("="*60)

        for source in sources:
            print(f"\nID: {source.id}")
            print(f"  Name:     {source.name}")
            print(f"  Category: {source.category.value}")
            print(f"  Method:   {source.ingest_method.value}")
            print(f"  Status:   {source.status.value}")
            print(f"  Priority: {source.priority}")
            print(f"  URL:      {source.base_url}")
            if source.feed_url:
                print(f"  Feed:     {source.feed_url}")
            if source.last_fetched_at:
                print(f"  Last fetch: {source.last_fetched_at}")

    finally:
        db.close()


def list_clusters(limit: int = 20):
    """List recent clusters."""
    db = SessionLocal()
    try:
        clusters = db.query(Cluster).filter(
            Cluster.status == ClusterStatus.ACTIVE
        ).order_by(
            Cluster.last_seen_at.desc()
        ).limit(limit).all()

        print("="*60)
        print(f"RECENT CLUSTERS (showing {len(clusters)} of {limit} requested)")
        print("="*60)

        for cluster in clusters:
            print(f"\nID: {cluster.id}")
            print(f"  Headline:     {cluster.headline}")
            print(f"  Event Type:   {cluster.event_type.value if hasattr(cluster.event_type, 'value') else cluster.event_type}")
            print(f"  Sources:      {cluster.source_count}")
            print(f"  First seen:   {cluster.first_seen_at}")
            print(f"  Last updated: {cluster.last_seen_at}")

    finally:
        db.close()


def show_tag_distribution():
    """Show tag distribution across clusters."""
    from app.core.queries import get_tag_distribution

    db = SessionLocal()
    try:
        distribution = get_tag_distribution(db)

        print("="*60)
        print("TAG DISTRIBUTION")
        print("="*60)

        for tag_info in distribution:
            print(f"{tag_info['name']:20} {tag_info['cluster_count']:>5} clusters")

    finally:
        db.close()


def list_entities(entity_type: str = None, limit: int = 50):
    """List entities."""
    db = SessionLocal()
    try:
        query = db.query(Entity)

        if entity_type:
            query = query.filter(Entity.entity_type == entity_type)

        entities = query.order_by(Entity.name).limit(limit).all()

        print("="*60)
        print(f"ENTITIES ({len(entities)} shown)")
        if entity_type:
            print(f"Filtered by type: {entity_type}")
        print("="*60)

        current_type = None
        for entity in entities:
            if entity.entity_type != current_type:
                current_type = entity.entity_type
                print(f"\n{current_type.upper()}:")

            print(f"  {entity.name:30} (slug: {entity.slug})")

    finally:
        db.close()


def reset_database():
    """Reset database (delete all data)."""
    print("="*60)
    print("WARNING: DATABASE RESET")
    print("="*60)
    print("\nThis will DELETE ALL DATA from the database.")
    print("This includes:")
    print("  - All sources")
    print("  - All ingested items and variants")
    print("  - All clusters")
    print("  - All submissions")
    print("  - Tags and entities will be preserved")
    print("\nThis action CANNOT be undone!")

    confirm = input("\nType 'DELETE ALL DATA' to confirm: ")

    if confirm != "DELETE ALL DATA":
        print("\n✗ Reset cancelled.")
        return

    db = SessionLocal()
    try:
        print("\nDeleting data...")

        # Delete in order to respect foreign keys
        db.query(Submission).delete()
        print("  ✓ Deleted submissions")

        db.query(CandidateSource).delete()
        print("  ✓ Deleted candidate sources")

        # ClusterVariant, ClusterTag, ClusterEntity will cascade delete
        db.query(Cluster).delete()
        print("  ✓ Deleted clusters (and mappings)")

        db.query(StoryVariant).delete()
        print("  ✓ Deleted story variants")

        db.query(RawItem).delete()
        print("  ✓ Deleted raw items")

        db.query(Source).delete()
        print("  ✓ Deleted sources")

        db.commit()

        print("\n✓ Database reset complete!")
        print("\nNext steps:")
        print("  1. Re-import sources: python -m app.scripts.import_sources initial_sources.csv")
        print("  2. Seed entities: python -m app.scripts.seed_entities")

    except Exception as e:
        db.rollback()
        print(f"\n✗ Error during reset: {e}")
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    try:
        if command == 'status':
            show_status()

        elif command == 'sources':
            list_sources()

        elif command == 'clusters':
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            list_clusters(limit)

        elif command == 'tags':
            show_tag_distribution()

        elif command == 'entities':
            entity_type = sys.argv[2] if len(sys.argv) > 2 else None
            list_entities(entity_type)

        elif command == 'reset':
            reset_database()

        else:
            print(f"Unknown command: {command}")
            print(__doc__)
            sys.exit(1)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
