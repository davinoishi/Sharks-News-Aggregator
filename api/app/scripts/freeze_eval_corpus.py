#!/usr/bin/env python3
"""
Freeze a labelled-eval corpus out of the live database (brief 16, EV-2).

**Time-sensitive.** ``run_purge_old_items`` deletes ``raw_items`` after 30 days,
so anything not captured stops existing. This script is shipped ahead of the
rest of brief 16 for that reason alone: capture is urgent, labelling is not.
Snapshot now, label later — the file will still be there.

Usage:
    python -m app.scripts.freeze_eval_corpus [--out PATH] [--per-stratum N]

Example (on the Pi):
    docker compose exec api python -m app.scripts.freeze_eval_corpus \\
        --out /app/eval_corpus/corpus-2026-08-19.jsonl

Writes two JSONL files next to each other:

    <out>              one record per raw_item
    <out>.pairs.jsonl  candidate variant pairs drawn from multi-variant clusters

**Sampling is stratified, not recent-first.** A corpus of only hard cases
measures the wrong thing, and a corpus of only recent items measures August. The
strata are:

    accepted            became a story_variant — the ordinary case, the control
    ingest_stub         rejected by the ingest-time stub filter and kept on
                        purpose (INGEST_STUB_FLAG). These are the only
                        HIGH-CONFIDENCE low_value positives: a rule matched
                        them, so the label is not a guess. Before that flag
                        existed these rows were discarded outright and
                        low_value could not be measured at all.
    low_value_suspect   relevance-approved but never became a variant, which is
                        how an LLM-flagged low_value stub looks after the fact
                        (that flag is still not persisted — enrich.py just
                        skips). Weaker label than ingest_stub: "no variant" has
                        other causes.
    rejected            relevance rejected it
    llm_compared        carries both a keyword result and an LLM response —
                        the RM-2 seam. Not "disagreed": that cannot be filtered
                        in SQL while llm_response is truncated (EV-1), so both
                        verdicts are captured per item and the analysis decides
    clustered           member of a multi-variant cluster, for pair labelling

**Labels are provisional.** Fields under ``labels`` are derived from what
production actually did, and production is what is under test — so they are a
starting point for a human pass, never ground truth. Every record carries
``label_source: "derived"``; change it to ``"human"`` on the ones you verify.

**Storage.** The output is third-party article text and is deliberately *not*
committed: see R3-A1 on keeping bulk data dumps out of the repo. Keep it with
the backups (which go off-device per R3-O1). Only the small hand-labelled pair
file lives in git.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import Text, func

from app.core.database import SessionLocal
from app.models import Cluster, ClusterVariant, RawItem, Source, StoryVariant
from app.models.validation_log import ValidationLog, ValidationResult
from app.tasks.ingest import INGEST_STUB_FLAG

STRATA = (
    "accepted",
    "ingest_stub",
    "low_value_suspect",
    "rejected",
    "llm_compared",
    "clustered",
)


def _record(raw, source, variant, log, cluster_id, stratum):
    """One corpus row. Mirrors what the enrich task actually sees as input.

    ``cluster_id`` is passed in rather than read off the variant: StoryVariant
    has no cluster_id column, and the cluster link lives in the ClusterVariant
    junction. (clustering.py assigns ``variant.cluster_id`` in four places;
    those are transient attribute sets that never persist — see the note in
    RM-4 follow-ups.)
    """
    return {
        "raw_item_id": raw.id,
        "stratum": stratum,
        "url": raw.canonical_url or raw.original_url,
        "source_name": source.name if source else None,
        "source_category": getattr(source.category, "value", None) if source else None,
        "title": raw.raw_title,
        "description": raw.raw_description,
        "published_at": raw.published_at.isoformat() if raw.published_at else None,
        "entity_ids": list(variant.entities or []) if variant else list(log.entities_found or []) if log else [],
        "variant_id": variant.id if variant else None,
        "cluster_id": cluster_id,
        "event_type": getattr(variant.event_type, "value", None) if variant else None,
        "llm_summary": (variant.extra_metadata or {}).get("llm_summary") if variant else None,
        # The keyword-vs-LLM comparison RM-2 turns on. Still kept as raw
        # fields rather than a derived "disagreed" boolean, so the analysis can
        # redo the comparison however it likes. ``llm_relevant`` is the parsed
        # verdict written at log time (EV-1); rows predating that column carry
        # a backfilled value where it was recoverable and NULL where it was
        # not — NULL means unknown, never rejected.
        "validation": {
            "method": getattr(log.method, "value", None) if log else None,
            "result": getattr(log.result, "value", None) if log else None,
            "keyword_matched": log.keyword_matched if log else None,
            "llm_relevant": log.llm_relevant if log else None,
            "llm_response": log.llm_response if log else None,
            "llm_reason": log.llm_reason if log else None,
            "llm_model": log.llm_model if log else None,
            "llm_confidence": log.llm_confidence if log else None,
        },
        "labels": {
            # What production did, not what is correct. Under test.
            "relevant": (log.result == ValidationResult.APPROVED) if log else (variant is not None),
            "low_value": stratum in ("ingest_stub", "low_value_suspect"),
            # ingest_stub is a rule match, not an inference — the only label in
            # this corpus that is not derived from a decision under test.
            "low_value_confidence": "high" if stratum == "ingest_stub" else "derived",
            "keyword_matched": log.keyword_matched if log else None,
        },
        "label_source": "derived",
    }


def _collect(db, per_stratum):
    """Gather up to ``per_stratum`` raw_items for each stratum, oldest first.

    Oldest-first on purpose: the oldest rows are the ones about to be purged,
    which is the whole reason this script exists.
    """
    picked = {}

    def add(rows, stratum):
        taken = 0
        for raw, source, variant, log, cluster_id in rows:
            if raw.id in picked or taken >= per_stratum:
                continue
            picked[raw.id] = _record(raw, source, variant, log, cluster_id, stratum)
            taken += 1
        return taken

    base = (
        db.query(RawItem, Source, StoryVariant, ValidationLog, ClusterVariant.cluster_id)
        .join(Source, Source.id == RawItem.source_id)
        .outerjoin(StoryVariant, StoryVariant.raw_item_id == RawItem.id)
        .outerjoin(ValidationLog, ValidationLog.raw_item_id == RawItem.id)
        .outerjoin(ClusterVariant, ClusterVariant.variant_id == StoryVariant.id)
        .order_by(RawItem.created_at)
    )

    counts = {}
    # First: a rule matched these, so the label is solid. Taking them before the
    # broader strata also stops an over-broad filter from claiming them.
    counts["ingest_stub"] = add(
        base.filter(
            RawItem.extra_metadata.cast(Text).contains(f'"{INGEST_STUB_FLAG}": true')
        ).all(),
        "ingest_stub",
    )
    # Named for what the filter actually selects: rows carrying BOTH a keyword
    # result and an LLM response. Whether they *disagree* cannot be expressed in
    # SQL while llm_response is a truncated String(100) (EV-1) — the verdict
    # needs a prefix match on the stored JSON. Capture both signals per item and
    # let the analysis decide; over-selecting here is the safe direction, since
    # the alternative is discovering after the purge that the row was not kept.
    counts["llm_compared"] = add(
        base.filter(
            ValidationLog.keyword_matched.isnot(None),
            ValidationLog.llm_response.isnot(None),
            ValidationLog.result != ValidationResult.ERROR,
        ).all(),
        "llm_compared",
    )
    counts["rejected"] = add(
        base.filter(ValidationLog.result == ValidationResult.REJECTED).all(), "rejected"
    )
    counts["low_value_suspect"] = add(
        base.filter(
            StoryVariant.id.is_(None),
            ValidationLog.result == ValidationResult.APPROVED,
        ).all(),
        "low_value_suspect",
    )
    counts["clustered"] = add(
        base.filter(ClusterVariant.cluster_id.isnot(None)).all(), "clustered"
    )
    counts["accepted"] = add(base.filter(StoryVariant.id.isnot(None)).all(), "accepted")

    return picked, counts


def _candidate_pairs(db, limit):
    """Variant pairs from multi-variant clusters, for should_merge labelling.

    Emitted unlabelled (``should_merge: null``). A pair that production merged
    is exactly what is under test — auto-labelling these ``true`` would bake the
    RM-4 defect into the eval set as ground truth.
    """
    multi = (
        db.query(ClusterVariant.cluster_id)
        .group_by(ClusterVariant.cluster_id)
        .having(func.count(ClusterVariant.variant_id) > 1)
        .all()
    )
    pairs = []
    for (cluster_id,) in multi:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        rows = (
            db.query(StoryVariant)
            .join(ClusterVariant, ClusterVariant.variant_id == StoryVariant.id)
            .filter(ClusterVariant.cluster_id == cluster_id)
            .order_by(StoryVariant.published_at)
            .all()
        )
        for i in range(len(rows) - 1):
            for j in range(i + 1, len(rows)):
                pairs.append({
                    "cluster_id": cluster_id,
                    "cluster_headline": cluster.headline if cluster else None,
                    "a_variant_id": rows[i].id,
                    "a_title": rows[i].title,
                    "b_variant_id": rows[j].id,
                    "b_title": rows[j].title,
                    "production_merged": True,
                    "should_merge": None,
                    "label_source": "unlabelled",
                })
                if len(pairs) >= limit:
                    return pairs
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = f"eval_corpus/corpus-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    parser.add_argument("--out", default=default, help=f"output path (default: {default})")
    parser.add_argument("--per-stratum", type=int, default=150,
                        help="max items per stratum (default: 150)")
    parser.add_argument("--max-pairs", type=int, default=400,
                        help="max candidate pairs (default: 400)")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        records, counts = _collect(db, args.per_stratum)
        pairs = _candidate_pairs(db, args.max_pairs)
    finally:
        db.close()

    if not records:
        print("No raw_items found — nothing to freeze.")
        return 1

    with out.open("w") as fh:
        for record in records.values():
            fh.write(json.dumps(record) + "\n")

    pairs_path = Path(str(out) + ".pairs.jsonl")
    with pairs_path.open("w") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair) + "\n")

    print("=" * 60)
    print("EVAL CORPUS FROZEN")
    print("=" * 60)
    print(f"\n{out}  —  {len(records)} items")
    for stratum in STRATA:
        print(f"  {stratum:20s} {counts.get(stratum, 0)}")
    print(f"\n{pairs_path}  —  {len(pairs)} candidate pairs (unlabelled)")
    print("\nLabels are DERIVED from what production did, which is what is")
    print("under test. Verify them by hand and set label_source to 'human'.")
    print("Keep these files with the backups, not in git (R3-A1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
