#!/usr/bin/env python3
"""
Replay ingested items through the OLD and NEW relevance predicates and diff them.

Answers the only question that matters before shipping a relevance change:
which real articles change verdict, and are the new rejections actually
rubbish? Prints every changed item so the newly-rejected list can be read by
eye — a count alone can't tell a rugby story from a Barracuda call-up.

Usage:
    python -m app.scripts.measure_relevance_change [--days 30] [--limit N]
                                                   [--source-id N] [--all]

    --days       window of raw_items to replay, by fetched_at (default 30)
    --limit      cap items replayed, newest first (default: no cap)
    --source-id  restrict to one source (e.g. the Google Alerts feed)
    --all        also list items whose verdict did NOT change

The OLD predicate is inlined below rather than imported: it no longer exists in
the codebase, and a comparison against a moving target measures nothing.

Read-only — opens a session, writes nothing.
"""
import argparse
import sys
from collections import Counter
from datetime import timedelta

from app.core.database import SessionLocal
from app.core.datetime_utils import utcnow
from app.enrichment.classify import (
    _STRONG_SHARKS_KEYWORDS,
    _WEAK_SHARKS_KEYWORDS,
    check_sharks_relevance,
    has_hockey_context,
    is_wrong_sport,
)
from app.enrichment.entities import extract_entities
from app.models import Entity, RawItem, Source
from app.tasks.enrich import effective_description

# The pre-RM-3 keyword list, frozen. Bare 'sharks' and the two venues sat in the
# same undifferentiated tier as 'san jose sharks'.
_OLD_SHARKS_KEYWORDS = (
    'sharks',
    'sj sharks',
    'san jose sharks',
    'barracuda',
    'sap center',
    'tech ccs arena',
)


def old_check_sharks_relevance(title, entity_ids, non_team_ids):
    """check_sharks_relevance as it stood before RM-3."""
    text_lower = (title or '').lower()
    if any(keyword in text_lower for keyword in _OLD_SHARKS_KEYWORDS):
        return True
    return any(eid in non_team_ids for eid in entity_ids)


def classify_change(title, url, entity_ids, non_team_ids, source_is_hockey):
    """Which gate in the new predicate decided this item."""
    text_lower = (title or '').lower()

    if is_wrong_sport(title, url):
        return "wrong_sport"
    if any(kw in text_lower for kw in _STRONG_SHARKS_KEYWORDS):
        return "strong_keyword"
    if any(eid in non_team_ids for eid in entity_ids):
        return "entity_match"
    if any(kw in text_lower for kw in _WEAK_SHARKS_KEYWORDS):
        if has_hockey_context(title, url, source_is_hockey):
            return "weak_keyword_corroborated"
        return "weak_keyword_uncorroborated"
    return "no_signal"


def replay(db, days, limit, source_id, show_all):
    cutoff = utcnow() - timedelta(days=days)

    query = (
        db.query(RawItem)
        .filter(RawItem.fetched_at >= cutoff)
        .order_by(RawItem.fetched_at.desc())
    )
    if source_id is not None:
        query = query.filter(RawItem.source_id == source_id)
    if limit:
        query = query.limit(limit)

    items = query.all()
    if not items:
        print(f"No raw_items in the last {days} days"
              + (f" for source {source_id}" if source_id else ""))
        return 0

    sources = {s.id: s for s in db.query(Source).all()}

    # One read of the entity table for the whole replay: extract_entities would
    # otherwise re-query it per item, thousands of times over a 30-day window.
    all_entities = db.query(Entity).all()
    non_team_ids = {e.id for e in all_entities if e.entity_type != 'team'}

    newly_rejected = []
    newly_approved = []
    unchanged = Counter()
    reasons = Counter()

    for item in items:
        source = sources.get(item.source_id)
        source_metadata = (getattr(source, "extra_metadata", None) or {})

        # Mirror enrich_raw_item exactly: dedicated sources never reach the
        # relevance gate at all, so counting them would inflate both columns.
        if source_metadata.get('skip_relevance_check'):
            unchanged['skipped_source'] += 1
            continue

        title = item.raw_title or ''
        url = item.canonical_url or item.original_url or ''
        description = effective_description(source_metadata, item.raw_description)
        entity_ids = extract_entities(
            db, f"{title} {description}".strip(), entities=all_entities
        )
        source_is_hockey = bool(source_metadata.get('hockey_scoped'))

        old = old_check_sharks_relevance(title, entity_ids, non_team_ids)
        new = check_sharks_relevance(db, title, entity_ids, url, source_is_hockey)

        reason = classify_change(title, url, entity_ids, non_team_ids, source_is_hockey)
        row = (item.id, title, url, reason, source.name if source else '?')

        if old and not new:
            newly_rejected.append(row)
            reasons[reason] += 1
        elif new and not old:
            newly_approved.append(row)
        else:
            unchanged['approved' if new else 'rejected'] += 1

    _report(items, newly_rejected, newly_approved, unchanged, reasons, days, show_all)
    return len(newly_rejected)


def _print_rows(rows):
    for item_id, title, url, reason, source_name in rows:
        print(f"  [{item_id}] {title[:96]}")
        print(f"        reason={reason}  source={source_name}")
        if url:
            print(f"        {url[:110]}")


def _report(items, newly_rejected, newly_approved, unchanged, reasons, days, show_all):
    gated = len(items) - unchanged['skipped_source']

    print("=" * 78)
    print(f"RELEVANCE PREDICATE DIFF — last {days} days")
    print("=" * 78)
    print(f"raw_items replayed:        {len(items)}")
    print(f"  reached the gate:        {gated}")
    print(f"  skip_relevance_check:    {unchanged['skipped_source']}")
    print()
    print(f"unchanged (approved):      {unchanged['approved']}")
    print(f"unchanged (rejected):      {unchanged['rejected']}")
    print(f"NEWLY REJECTED:            {len(newly_rejected)}"
          + (f"  ({len(newly_rejected) / gated:.1%} of gated)" if gated else ""))
    print(f"newly approved:            {len(newly_approved)}")

    if reasons:
        print("\nNewly rejected, by reason:")
        for reason, count in reasons.most_common():
            print(f"  {reason:32} {count}")

    if newly_rejected:
        print("\n" + "-" * 78)
        print("NEWLY REJECTED — read these. Any real Sharks story here is a regression.")
        print("-" * 78)
        _print_rows(newly_rejected)

    if newly_approved:
        print("\n" + "-" * 78)
        print("NEWLY APPROVED (expected: none — RM-3 only narrows)")
        print("-" * 78)
        _print_rows(newly_approved)

    if show_all:
        print("\n" + "-" * 78)
        print("Unchanged counts are summarized above; re-run without --all for brevity.")
        print("-" * 78)


def main():
    parser = argparse.ArgumentParser(
        description="Diff the old and new Sharks relevance predicates over ingested history"
    )
    parser.add_argument("--days", type=int, default=30, help="window in days (default 30)")
    parser.add_argument("--limit", type=int, default=None, help="cap items replayed")
    parser.add_argument("--source-id", type=int, default=None, help="restrict to one source")
    parser.add_argument("--all", action="store_true", help="also note unchanged items")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        replay(db, args.days, args.limit, args.source_id, args.all)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
