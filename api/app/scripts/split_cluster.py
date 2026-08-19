#!/usr/bin/env python3
"""
Split variants out of a cluster into a new cluster (RM-4 / brief 14, CM-7).

The inverse of merge_clusters.py. Brief 14's gates only affect *new* clustering
decisions — nothing re-clusters historical variants — so the over-merged cards
RM-4 measured stay on the feed until they are split by hand.

Usage:
    python -m app.scripts.split_cluster <cluster_id> <variant_ids...> [--dry-run]

Example:
    python -m app.scripts.split_cluster 4152 8821 8822 --dry-run

The named variants move to a brand-new cluster. Both clusters then have their
derived fields recomputed from their actual membership: source_count, tokens,
entities_agg, first_seen_at, last_seen_at, the entity/tag junctions, and the
headline (via select_cluster_headline).

Note on source_count: it is incremented on join and never decremented after the
30-day variant purge, so stored values over-report badly — one production
cluster claimed 64 sources while holding 7 variants. This script recomputes it
by query for both sides rather than trusting the stored number. The general fix
is tracked as R2-F4.
"""
import sys

from app.core.database import SessionLocal
from app.core.datetime_utils import ensure_aware, utcnow
from app.enrichment.clustering import (
    add_cluster_entity_associations,
    normalize_tokens,
    select_cluster_headline,
)
from app.models import Cluster, ClusterStatus, ClusterTag, ClusterVariant, StoryVariant


def _recompute(db, cluster):
    """Rebuild every derived field on ``cluster`` from its actual membership."""
    rows = (
        db.query(StoryVariant)
        .join(ClusterVariant, ClusterVariant.variant_id == StoryVariant.id)
        .filter(ClusterVariant.cluster_id == cluster.id)
        .all()
    )
    if not rows:
        return 0

    tokens = set()
    entities = set()
    times = []
    for v in rows:
        tokens.update(v.tokens or normalize_tokens(v.title or ""))
        entities.update(v.entities or [])
        aware = ensure_aware(v.published_at)
        if aware:
            times.append(aware)

    cluster.tokens = sorted(tokens)
    cluster.entities_agg = sorted(entities)
    cluster.source_count = len(rows)
    if times:
        cluster.first_seen_at = min(times)
        cluster.last_seen_at = max(times)
    cluster.updated_at = utcnow()

    add_cluster_entity_associations(db, cluster, list(entities))

    headline = select_cluster_headline(db, cluster)
    if headline:
        cluster.headline = headline

    return len(rows)


def split_cluster(cluster_id: int, variant_ids: list[int], dry_run: bool = False):
    """Move ``variant_ids`` out of ``cluster_id`` and into a new cluster."""
    if not variant_ids:
        print("Error: name at least one variant to split out")
        return False

    db = SessionLocal()
    try:
        source = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not source:
            print(f"Error: cluster {cluster_id} not found")
            return False

        links = (
            db.query(ClusterVariant)
            .filter(
                ClusterVariant.cluster_id == cluster_id,
                ClusterVariant.variant_id.in_(variant_ids),
            )
            .all()
        )
        found = {link.variant_id for link in links}
        missing = set(variant_ids) - found
        if missing:
            print(f"Error: variants not in cluster {cluster_id}: {sorted(missing)}")
            return False

        total = (
            db.query(ClusterVariant)
            .filter(ClusterVariant.cluster_id == cluster_id)
            .count()
        )
        if len(found) >= total:
            print("Error: that would move every variant — nothing to split from")
            return False

        moving = (
            db.query(StoryVariant)
            .filter(StoryVariant.id.in_(sorted(found)))
            .order_by(StoryVariant.published_at)
            .all()
        )

        print("=" * 60)
        print("CLUSTER SPLIT")
        print("=" * 60)
        print(f"\nSource cluster #{cluster_id}: {source.headline}")
        print(f"  Variants: {total} (stored source_count: {source.source_count})")
        print(f"\nMoving {len(moving)} variant(s) to a new cluster:")
        for v in moving:
            published = (v.published_at or "")
            print(f"  #{v.id} {str(published)[:16]}  {(v.title or '')[:66]}")
        print(f"\nRemaining in #{cluster_id}: {total - len(moving)} variant(s)")

        if dry_run:
            print("\n[DRY RUN] No changes made.")
            return True

        confirm = input("\nProceed with split? [y/N]: ")
        if confirm.lower() != "y":
            print("Split cancelled.")
            return False

        seed = moving[0]
        new_cluster = Cluster(
            headline=seed.title or "Untitled",
            event_type=source.event_type,
            status=ClusterStatus.ACTIVE,
            first_seen_at=ensure_aware(seed.published_at) or utcnow(),
            last_seen_at=ensure_aware(seed.published_at) or utcnow(),
            source_count=0,
            tokens=[],
            entities_agg=[],
        )
        db.add(new_cluster)
        db.flush()

        # The ClusterVariant junction IS the cluster link. StoryVariant has no
        # cluster_id column, so there is nothing to update on the variant rows
        # themselves (clustering.py assigns variant.cluster_id in four places;
        # those are transient attribute sets that never reach the database).
        for link in links:
            link.cluster_id = new_cluster.id
        db.flush()

        # Carry the source cluster's tags over as a starting point. They are
        # recomputed from titles on the next enrichment pass; copying avoids a
        # brand-new cluster appearing untagged on the feed in the meantime.
        for ct in db.query(ClusterTag).filter(ClusterTag.cluster_id == cluster_id).all():
            db.add(ClusterTag(cluster_id=new_cluster.id, tag_id=ct.tag_id))
        db.flush()

        moved = _recompute(db, new_cluster)
        kept = _recompute(db, source)
        db.commit()

        print(f"\n✓ New cluster #{new_cluster.id}: {new_cluster.headline}")
        print(f"    {moved} variant(s), {new_cluster.first_seen_at} → {new_cluster.last_seen_at}")
        print(f"✓ Cluster #{cluster_id}: {source.headline}")
        print(f"    {kept} variant(s), {source.first_seen_at} → {source.last_seen_at}")
        return True

    except Exception as exc:
        db.rollback()
        print(f"Error: {exc}")
        raise
    finally:
        db.close()


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]

    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    try:
        cluster_id = int(args[0])
        variant_ids = [int(a) for a in args[1:]]
    except ValueError:
        print("Error: cluster id and variant ids must be integers")
        sys.exit(1)

    sys.exit(0 if split_cluster(cluster_id, variant_ids, dry_run) else 1)


if __name__ == "__main__":
    main()
