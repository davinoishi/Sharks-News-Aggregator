#!/usr/bin/env python3
"""
Score the clustering matcher against labelled pairs (brief 15, SK-7).

Reports merge **precision and recall separately**. A single accuracy number
hides exactly the trade this work is making — brief 14 deliberately buys
precision with recall — and reporting one number is how the RM-3 regression
stayed invisible for a month.

Usage:
    python -m app.scripts.eval_pairs --database-url postgresql://... \\
        [--pairs api/eval/pairs.seed.jsonl]

**Requires an explicit --database-url, and it must not be production.** The
harness seeds sources, entities and variants to drive the real
``match_or_create_cluster``, so it needs a scratch Postgres that it **wipes
between every pair**. It refuses a URL whose database name looks like the
production one.

Wiping, not rolling back, is load-bearing: ``match_or_create_cluster`` commits
internally (four times), so a rollback around it undoes nothing. An earlier
version relied on rollback and silently let every pair see the clusters built
by every previous pair — with "Macklin Celebrini Card Auction Nears $500K"
appearing in five pairs, later comparisons were being scored against a cluster
that already held pipeline-ranking articles. It reported plausible numbers that
meant nothing.

Postgres only: clusters and story_variants use ARRAY columns.

Why it drives the real matcher rather than recomputing the gates: a harness
with its own copy of the decision logic measures the copy. The same reasoning
that keeps brief 16's replay harness on the real prompt builders.

Pair file format (JSONL), matching ``api/eval/pairs.seed.jsonl``:

    {"a_title": "...", "b_title": "...", "should_merge": true,
     "label_source": "human", "provenance": "cluster 4152"}

Optional per-pair fields, applied to both sides unless suffixed ``_a``/``_b``:
``entities`` (list of names), ``event_type``, ``story_key_a``/``story_key_b``,
``summary_a``/``summary_b``.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DEFAULT_PAIRS = "eval/pairs.seed.jsonl"

# Refuse to touch a URL whose database name contains any of these.
_PROD_MARKERS = ("sharks_prod", "sharks_news", "production")


def _guard_database_url(url: str) -> None:
    if not url.startswith(("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")):
        raise SystemExit("--database-url must be a PostgreSQL URL (ARRAY columns).")
    db_name = url.rsplit("/", 1)[-1].split("?")[0].lower()
    for marker in _PROD_MARKERS:
        if marker in db_name:
            raise SystemExit(
                f"Refusing to run against a database named {db_name!r} — this "
                "harness writes. Point it at a scratch database."
            )


def _load_pairs(path: Path) -> list:
    pairs = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: {exc}") from exc
        if record.get("should_merge") is None:
            continue  # unlabelled candidate pairs are not scoreable
        pairs.append(record)
    return pairs


def _reset(engine) -> None:
    """Truncate every table between pairs.

    Each pair must be scored as if it were the only thing the matcher had ever
    seen. ``match_or_create_cluster`` commits, so isolation cannot come from a
    transaction — it has to be a wipe.
    """
    from app.core.database import Base

    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


def _run_pair(db, record, seq):
    """Cluster both sides of one pair, return True if they landed together."""
    from app.enrichment.clustering import match_or_create_cluster, normalize_tokens
    from app.models import (
        Entity,
        EventType,
        IngestMethod,
        RawItem,
        Source,
        SourceCategory,
        StoryVariant,
    )

    source = Source(
        name=f"EvalSrc{seq}",
        category=SourceCategory.PRESS,
        ingest_method=IngestMethod.RSS,
        base_url=f"https://eval-{seq}.example.com",
    )
    db.add(source)
    db.flush()

    entity_ids = []
    for name in record.get("entities", []):
        slug = Entity.make_slug(name)
        entity = db.query(Entity).filter(Entity.slug == slug).first()
        if not entity:
            entity_type = "team" if "sharks" in name.lower() else "player"
            entity = Entity(name=name, slug=slug, entity_type=entity_type)
            db.add(entity)
            db.flush()
        entity_ids.append(entity.id)

    event_type = record.get("event_type", "other")
    now = datetime.utcnow()
    cluster_ids = []

    for side in ("a", "b"):
        title = record[f"{side}_title"]
        url = f"https://eval-{seq}.example.com/{side}"
        raw = RawItem(
            source_id=source.id, original_url=url, canonical_url=url, raw_title=title
        )
        db.add(raw)
        db.flush()

        extra = {}
        if record.get(f"summary_{side}"):
            extra["llm_summary"] = record[f"summary_{side}"]
        if record.get(f"story_key_{side}"):
            extra["story_key"] = record[f"story_key_{side}"]

        variant = StoryVariant(
            raw_item_id=raw.id,
            source_id=source.id,
            url=url,
            title=title,
            published_at=now,
            tokens=normalize_tokens(title),
            entities=list(entity_ids),
            event_type=EventType(event_type),
            extra_metadata=extra,
        )
        db.add(variant)
        db.flush()

        cluster_ids.append(
            match_or_create_cluster(
                db, variant, variant.tokens, entity_ids, event_type, source, tag_names=[]
            )
        )

    return cluster_ids[0] == cluster_ids[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True, help="scratch PostgreSQL URL")
    parser.add_argument("--pairs", default=DEFAULT_PAIRS)
    parser.add_argument("--verbose", action="store_true", help="list every mismatch")
    args = parser.parse_args()

    _guard_database_url(args.database_url)

    pairs_path = Path(args.pairs)
    if not pairs_path.exists():
        raise SystemExit(f"Pair file not found: {pairs_path}")
    pairs = _load_pairs(pairs_path)
    if not pairs:
        raise SystemExit(f"No labelled pairs in {pairs_path}")

    from app.core.database import Base
    from app.models import Cluster  # noqa: F401 — registers the mapper

    engine = create_engine(args.database_url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    tp = fp = tn = fn = 0
    mismatches = []

    for seq, record in enumerate(pairs):
        _reset(engine)
        db = session_factory()
        try:
            merged = _run_pair(db, record, seq)
        finally:
            db.close()

        expected = bool(record["should_merge"])
        if merged and expected:
            tp += 1
        elif merged and not expected:
            fp += 1
            mismatches.append(("OVER-MERGED", record))
        elif not merged and expected:
            fn += 1
            mismatches.append(("SPLIT", record))
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")

    print("=" * 64)
    print(f"CLUSTERING PAIR EVAL — {len(pairs)} labelled pairs from {pairs_path}")
    print("=" * 64)
    print(f"\n  merged & should      (TP): {tp}")
    print(f"  merged & should NOT  (FP): {fp}   <- the RM-4 failure")
    print(f"  split  & should NOT  (TN): {tn}")
    print(f"  split  & should      (FN): {fn}   <- the cost of the gates")
    print(f"\n  merge precision: {precision:.3f}")
    print(f"  merge recall   : {recall:.3f}")
    print("\nReported separately on purpose: brief 14 buys precision with recall,")
    print("and one blended number would hide exactly that trade.")

    if mismatches and args.verbose:
        print("\n--- mismatches ---")
        for kind, record in mismatches:
            print(f"\n  [{kind}] {record.get('provenance', '')}")
            print(f"    A: {record['a_title'][:70]}")
            print(f"    B: {record['b_title'][:70]}")

    # Non-zero only on a false merge: over-merging is the expensive failure and
    # the one this work exists to stop. A split is a known, accepted cost.
    return 1 if fp else 0


if __name__ == "__main__":
    sys.exit(main())
