#!/usr/bin/env python3
"""
Merge multiple clusters into one.

Usage:
    python -m app.scripts.merge_clusters <cluster_ids...>

Example:
    python -m app.scripts.merge_clusters 240 241 242 243

The first cluster ID will be the target. All variants from other clusters
will be moved to the target cluster, and the other clusters will be deleted.
"""
import sys
from datetime import datetime
from sqlalchemy import func

from app.core.database import SessionLocal
from app.models import Cluster, ClusterStatus
from app.models.cluster_variant import ClusterVariant
from app.models.cluster_tag import ClusterTag
from app.models.cluster_entity import ClusterEntity


def merge_clusters(cluster_ids: list[int], dry_run: bool = False):
    """Merge multiple clusters into the first one."""
    if len(cluster_ids) < 2:
        print("Error: Need at least 2 cluster IDs to merge")
        return False

    db = SessionLocal()
    try:
        # Load all clusters
        clusters = db.query(Cluster).filter(Cluster.id.in_(cluster_ids)).all()
        cluster_map = {c.id: c for c in clusters}

        # Validate all clusters exist
        for cid in cluster_ids:
            if cid not in cluster_map:
                print(f"Error: Cluster {cid} not found")
                return False

        target_id = cluster_ids[0]
        source_ids = cluster_ids[1:]
        target = cluster_map[target_id]

        print("=" * 60)
        print("CLUSTER MERGE")
        print("=" * 60)
        print(f"\nTarget cluster (keeping): #{target_id}")
        print(f"  Headline: {target.headline}")
        print(f"  Variants: {target.source_count}")

        print(f"\nSource clusters (merging into target):")
        total_variants = target.source_count
        for sid in source_ids:
            source = cluster_map[sid]
            print(f"  #{sid}: {source.headline[:60]}... ({source.source_count} variants)")
            total_variants += source.source_count

        print(f"\nTotal variants after merge: {total_variants}")

        if dry_run:
            print("\n[DRY RUN] No changes made.")
            return True

        # Confirm merge
        confirm = input("\nProceed with merge? [y/N]: ")
        if confirm.lower() != 'y':
            print("Merge cancelled.")
            return False

        print("\nMerging...")

        # 1. Move variants from source clusters to target
        for sid in source_ids:
            db.query(ClusterVariant).filter(
                ClusterVariant.cluster_id == sid
            ).update({ClusterVariant.cluster_id: target_id})
            print(f"  Moved variants from #{sid}")

        # 2. Move tags (avoid duplicates)
        existing_tags = set(
            t.tag_id for t in db.query(ClusterTag).filter(
                ClusterTag.cluster_id == target_id
            ).all()
        )
        for sid in source_ids:
            source_tags = db.query(ClusterTag).filter(
                ClusterTag.cluster_id == sid
            ).all()
            for ct in source_tags:
                if ct.tag_id not in existing_tags:
                    ct.cluster_id = target_id
                    existing_tags.add(ct.tag_id)
                else:
                    db.delete(ct)
            print(f"  Merged tags from #{sid}")

        # 3. Move entities (avoid duplicates)
        existing_entities = set(
            e.entity_id for e in db.query(ClusterEntity).filter(
                ClusterEntity.cluster_id == target_id
            ).all()
        )
        for sid in source_ids:
            source_entities = db.query(ClusterEntity).filter(
                ClusterEntity.cluster_id == sid
            ).all()
            for ce in source_entities:
                if ce.entity_id not in existing_entities:
                    ce.cluster_id = target_id
                    existing_entities.add(ce.entity_id)
                else:
                    db.delete(ce)
            print(f"  Merged entities from #{sid}")

        # 4. Update target cluster metadata
        # Get earliest first_seen and latest last_seen
        earliest = min(cluster_map[cid].first_seen_at for cid in cluster_ids)
        latest = max(cluster_map[cid].last_seen_at for cid in cluster_ids)

        # Merge tokens from all clusters
        all_tokens = set(target.tokens or [])
        for sid in source_ids:
            all_tokens.update(cluster_map[sid].tokens or [])

        # Merge entity aggregations
        all_entities = set(target.entities_agg or [])
        for sid in source_ids:
            all_entities.update(cluster_map[sid].entities_agg or [])

        target.first_seen_at = earliest
        target.last_seen_at = latest
        target.tokens = list(all_tokens)
        target.entities_agg = list(all_entities)
        target.updated_at = datetime.utcnow()

        # 5. Update source count
        new_count = db.query(func.count(ClusterVariant.id)).filter(
            ClusterVariant.cluster_id == target_id
        ).scalar()
        target.source_count = new_count

        print(f"  Updated target metadata (source_count: {new_count})")

        # 6. Delete source clusters
        for sid in source_ids:
            db.query(Cluster).filter(Cluster.id == sid).delete()
            print(f"  Deleted cluster #{sid}")

        db.commit()

        print(f"\n✓ Successfully merged {len(source_ids)} clusters into #{target_id}")
        print(f"  Final source count: {target.source_count}")
        return True

    except Exception as e:
        db.rollback()
        print(f"\n✗ Error during merge: {e}")
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nError: Need at least 2 cluster IDs")
        sys.exit(1)

    # Parse cluster IDs
    try:
        cluster_ids = [int(arg) for arg in sys.argv[1:]]
    except ValueError:
        print("Error: All arguments must be integer cluster IDs")
        sys.exit(1)

    dry_run = '--dry-run' in sys.argv
    if dry_run:
        cluster_ids = [cid for cid in cluster_ids if cid != '--dry-run']

    success = merge_clusters(cluster_ids, dry_run=dry_run)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
