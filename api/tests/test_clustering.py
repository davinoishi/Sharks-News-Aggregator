"""Integration tests for match_or_create_cluster (brief 06).

Postgres-only: clusters/story_variants use ARRAY columns. Drives the real
clustering function with seeded variants and asserts merge/no-merge outcomes.
"""
import os
from datetime import datetime, timedelta

import pytest

from app.models import (
    Entity,
    EventType,
    IngestMethod,
    RawItem,
    Source,
    SourceCategory,
    StoryVariant,
)
from app.tasks.enrich import match_or_create_cluster, normalize_tokens

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="requires PostgreSQL (clusters/story_variants use ARRAY columns)",
)

_n = 0


def _source(db):
    s = Source(
        name="Src",
        category=SourceCategory.PRESS,
        ingest_method=IngestMethod.RSS,
        base_url="https://src.example.com",
    )
    db.add(s)
    db.flush()
    return s


def _entity(db, name, entity_type="player"):
    """Get-or-create a real Entity row.

    Entity IDs must resolve to rows: filter_team_entities() and
    entity_name_tokens() both query the table, so a bare integer would silently
    disable the entity path (which is how it went untested until RM-4).
    """
    slug = Entity.make_slug(name)
    existing = db.query(Entity).filter(Entity.slug == slug).first()
    if existing:
        return existing
    e = Entity(name=name, slug=slug, entity_type=entity_type)
    db.add(e)
    db.flush()
    return e


def _variant(db, source, title, published_at, event_type="signing", url=None,
             llm_summary=None, entity_ids=None):
    global _n
    _n += 1
    url = url or f"https://src.example.com/{_n}"
    raw = RawItem(source_id=source.id, original_url=url, canonical_url=url, raw_title=title)
    db.add(raw)
    db.flush()
    v = StoryVariant(
        raw_item_id=raw.id,
        source_id=source.id,
        url=url,
        title=title,
        published_at=published_at,
        tokens=normalize_tokens(title),
        entities=list(entity_ids or []),
        event_type=EventType(event_type),
        extra_metadata={"llm_summary": llm_summary} if llm_summary else {},
    )
    db.add(v)
    db.flush()
    return v


def _cluster(db, source, title, published_at, event_type="signing", url=None,
             llm_summary=None, entity_ids=None):
    entity_ids = list(entity_ids or [])
    v = _variant(db, source, title, published_at, event_type, url=url,
                 llm_summary=llm_summary, entity_ids=entity_ids)
    return match_or_create_cluster(
        db, v, v.tokens, entity_ids, event_type, source, tag_names=[]
    )


def test_same_story_two_sources_merge_into_one_cluster(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    title = "Celebrini signs eight year extension with the Sharks"
    cid1 = _cluster(pg_db, src, title, now)
    cid2 = _cluster(pg_db, src, title, now)  # syndicated copy → title match
    assert cid1 == cid2


@pytest.mark.parametrize("left,right,event_type", [
    (
        "Sharks news: San Jose signs former Rangers defenseman to one-year, two-way contract",
        "Sharks sign former Rangers defenseman to one-year, two-way contract - Yahoo Sports",
        "signing",
    ),
    (
        "BARRACUDA UPGRADE: Eric Comrie, Alex Barre-Boulet STRENGTHEN San Jose’s AHL PLAYOFF Push",
        "Eric Comrie, Alex Barre-Boulet STRENGTHEN San Jose's AHL PLAYOFF Push | cbs19.tv",
        "other",
    ),
    (
        # Rewritten headline for the same staff hire: "GM" vs "General
        # Manager" plus a dropped name. Merges via headline-to-headline
        # token overlap after abbreviation canonicalization.
        "Sharks Hire Jeff Kealty as Assistant General Manager",
        "Sharks Hire New Assistant GM - Yahoo Sports",
        "signing",
    ),
])
def test_reported_duplicate_pairs_merge_without_entities(
    pg_db, left, right, event_type
):
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(pg_db, src, left, now, event_type)
    cid2 = _cluster(pg_db, src, right, now, event_type)
    assert cid1 == cid2


def test_personnel_story_merges_across_event_types_via_shared_name(pg_db):
    # "Jeff Kealty" isn't in the entity table (staff, not roster), and the two
    # headlines disagree on event classification. The shared person-name bigram
    # plus moderate title overlap should still put them on one card.
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(
        pg_db, src,
        "Assistant GM Jeff Kealty departs Predators to pursue position with Sharks - Predlines",
        now, "other",
    )
    cid2 = _cluster(
        pg_db, src,
        "Sharks Hire Jeff Kealty as Assistant General Manager",
        now, "signing",
    )
    assert cid1 == cid2


def test_role_headline_merges_with_named_sibling_via_summary(pg_db):
    # One headline names the subject only by role ("first round draft pick");
    # its sibling names the person. The titles and entities share nothing, but
    # the LLM summaries both lead with the name and bridge them.
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(
        pg_db, src,
        "San Jose Sharks prospect Keaton Verhoeff to return to North Dakota - Times-Standard",
        now, "prospect",
        llm_summary="Keaton Verhoeff returns to North Dakota",
    )
    cid2 = _cluster(
        pg_db, src,
        "San Jose Sharks' first round draft pick finalizes plans for upcoming season",
        now, "prospect",
        llm_summary="Keaton Verhoeff finalizes upcoming season plans",
    )
    assert cid1 == cid2


def test_summary_bridge_keeps_different_people_apart(pg_db):
    # The summary bridge must key on a shared name, not merge every prospect
    # story from the same window.
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(
        pg_db, src,
        "Sharks prospect Kasper Halttunen scores twice for London",
        now, "prospect",
        llm_summary="Kasper Halttunen scores twice for London Knights",
    )
    cid2 = _cluster(
        pg_db, src,
        "Sharks' first round draft pick finalizes plans for upcoming season",
        now, "prospect",
        llm_summary="Keaton Verhoeff finalizes upcoming season plans",
    )
    assert cid1 != cid2


def test_shared_name_alone_does_not_merge_different_stories(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(
        pg_db, src,
        "Jeff Kealty builds out Sharks scouting department with three hires",
        now, "signing",
    )
    cid2 = _cluster(
        pg_db, src,
        "Jeff Kealty attends Predators alumni charity golf event",
        now, "other",
    )
    assert cid1 != cid2


def test_late_copies_use_publication_relative_window(pg_db):
    src = _source(pg_db)
    old_publication_time = datetime.utcnow() - timedelta(days=5)
    title = "Sharks sign Libor Hajek to a one year contract"
    cid1 = _cluster(pg_db, src, title, old_publication_time, "signing")
    cid2 = _cluster(pg_db, src, title, old_publication_time, "signing")
    assert cid1 == cid2


def test_cross_domain_shared_content_uuid_merges(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    content_id = "535-646a692c-dca4-4e11-aa72-38891f6d78af"
    cid1 = _cluster(
        pg_db,
        src,
        "Barracuda roster analysis",
        now,
        "other",
        url=f"https://www.kens5.com/video/story/{content_id}",
    )
    cid2 = _cluster(
        pg_db,
        src,
        "AHL playoff push video",
        now,
        "prospect",
        url=f"https://www.fox61.com/video/story/{content_id}",
    )
    assert cid1 == cid2


def test_unrelated_stories_do_not_merge(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    cid1 = _cluster(pg_db, src, "Celebrini signs eight year extension", now, "signing")
    cid2 = _cluster(pg_db, src, "Prospect drafted in third round shows promise", now, "prospect")
    assert cid1 != cid2


def test_game_articles_cluster_by_game_id(pg_db):
    src = _source(pg_db)
    # Must be within the 24h game window, so use "now" (same instant → same date).
    now = datetime.utcnow()
    cid1 = _cluster(pg_db, src, "Sharks fall to Boston 4-2", now, "game")
    cid2 = _cluster(pg_db, src, "Recap: San Jose drops contest against the Bruins", now, "game")
    assert cid1 == cid2  # same opponent (BOS) + same date → same game id


def test_time_window_respected(pg_db):
    src = _source(pg_db)
    now = datetime.utcnow()
    title = "Karlsson trade rumors continue to swirl"
    # First cluster is created ~100h ago — outside the 72h 'trade' window.
    cid_old = _cluster(pg_db, src, title, now - timedelta(hours=100), "trade")
    # An identical-title article today must NOT join the out-of-window cluster.
    cid_new = _cluster(pg_db, src, title, now, "trade")
    assert cid_old != cid_new


# --- headline selection ------------------------------------------------------

def test_headline_repick_replaces_an_unrepresentative_first_title(pg_db):
    """The card is named by the title that best describes the story, not by
    whichever variant happened to arrive first.

    Models the prod incident: a Google Alerts item whose description was the
    publisher's "Trending" sidebar got summarized as a Darnell Nurse trade story
    and created the cluster, so its unrelated title named the card even after two
    genuine Nurse articles joined.
    """
    from app.models import Cluster

    src = _source(pg_db)
    now = datetime.utcnow()
    summary = "Darnell Nurse trade to San Jose Sharks"

    cid = _cluster(
        pg_db, src,
        "Edmonton police to introduce involuntary detention detox",
        now, "trade", llm_summary=summary,
    )
    cluster = pg_db.query(Cluster).filter(Cluster.id == cid).first()
    assert cluster.headline == "Edmonton police to introduce involuntary detention detox"

    # A genuinely on-topic article joins the same cluster.
    joined = _cluster(
        pg_db, src,
        "Darnell Nurse trade to San Jose Sharks reshapes the blue line",
        now, "trade", llm_summary=summary,
    )
    assert joined == cid

    pg_db.refresh(cluster)
    assert cluster.headline == "Darnell Nurse trade to San Jose Sharks reshapes the blue line"


def test_headline_repick_keeps_the_incumbent_on_a_tie(pg_db):
    """A later variant that scores no better must not churn the headline.

    summary_similarity strips publication suffixes, so "X - Yahoo Sports" scores
    exactly like "X" — an exact tie, resolved in favour of the incumbent.
    """
    from app.models import Cluster

    src = _source(pg_db)
    now = datetime.utcnow()
    summary = "Celebrini contract extension"

    cid = _cluster(
        pg_db, src, "Celebrini signs contract extension with Sharks",
        now, "signing", llm_summary=summary,
    )
    joined = _cluster(
        pg_db, src, "Celebrini signs contract extension with Sharks - Yahoo Sports",
        now, "signing", llm_summary=summary,
    )
    assert joined == cid

    cluster = pg_db.query(Cluster).filter(Cluster.id == cid).first()
    pg_db.refresh(cluster)
    assert cluster.headline == "Celebrini signs contract extension with Sharks"


# --- RM-4 / brief 14: the entity path ----------------------------------------
#
# Every test above this line passes entities=[], so the 0.55-weight entity term
# in calculate_similarity_score() — the term that caused RM-4 — had no coverage
# at all. These hold entities and event type constant and vary only the topic,
# which is the shape of the production failure.

def _celebrini(db):
    return [
        _entity(db, "Macklin Celebrini").id,
        _entity(db, "San Jose Sharks", "team").id,
    ]


def test_same_player_same_event_different_story_does_not_merge(pg_db):
    """The reported card: a rookie-card auction and the pipeline rankings.

    Same player, same event type, zero shared vocabulary. Scored
    0.55*1.0 + 0.35*0.0 + 0.10*1.0 = 0.65 against a 0.62 bar and merged.
    """
    src = _source(pg_db)
    now = datetime.utcnow()
    entities = _celebrini(pg_db)
    cid1 = _cluster(
        pg_db, src, "Macklin Celebrini Card Auction Nears $500K & It's Not Done",
        now, "prospect", entity_ids=entities,
    )
    cid2 = _cluster(
        pg_db, src, "San Jose Sharks are No. 1 in NHL Pipeline Rankings for 2026",
        now, "prospect", entity_ids=entities,
    )
    assert cid1 != cid2


def test_star_player_cluster_does_not_absorb_unrelated_signing_news(pg_db):
    """From the 116-variant Celebrini extension cluster in production."""
    src = _source(pg_db)
    now = datetime.utcnow()
    entities = _celebrini(pg_db)
    cid1 = _cluster(
        pg_db, src, "Sharks sign Celebrini to 5-year, $94M extension",
        now, "signing", entity_ids=entities,
    )
    cid2 = _cluster(
        pg_db, src, "5 Restricted Free Agents Still Unsigned With Camp Approaching",
        now, "signing", entity_ids=entities,
    )
    assert cid1 != cid2


def test_star_player_cluster_does_not_absorb_countdown_filler(pg_db):
    """From the IIHF cluster, which had accumulated six unrelated stories."""
    src = _source(pg_db)
    now = datetime.utcnow()
    entities = _celebrini(pg_db)
    cid1 = _cluster(
        pg_db, src, "Macklin Celebrini Named IIHF Male Player of the Year",
        now, "prospect", entity_ids=entities,
    )
    cid2 = _cluster(
        pg_db, src, "71 Days to Opening Day: Macklin Celebrini",
        now, "prospect", entity_ids=entities,
    )
    assert cid1 != cid2


def test_same_story_still_merges_with_entities_present(pg_db):
    """The counter-test: the gate must not break real same-story merging."""
    src = _source(pg_db)
    now = datetime.utcnow()
    entities = _celebrini(pg_db)
    cid1 = _cluster(
        pg_db, src, "Macklin Celebrini Card Auction Nears $500K & It's Not Done",
        now, "prospect", entity_ids=entities,
    )
    cid2 = _cluster(
        pg_db, src, "Record-Setting Macklin Celebrini Card Highlights Goldin Auctions",
        now, "prospect", entity_ids=entities,
    )
    assert cid1 == cid2


def test_wire_syndication_still_merges_with_entities_present(pg_db):
    """The Graf re-signing: 52 variants in production and correct.

    This is the control for the whole brief — if it stops forming, the topical
    evidence gate has gone too far.
    """
    src = _source(pg_db)
    now = datetime.utcnow()
    entities = [
        _entity(pg_db, "Collin Graf").id,
        _entity(pg_db, "San Jose Sharks", "team").id,
    ]
    cid1 = _cluster(
        pg_db, src, "Sharks ink Graf to 3-year contract with $4.25M AAV",
        now, "signing", entity_ids=entities,
    )
    cid2 = _cluster(
        pg_db, src, "The Sharks re-sign F Collin Graf to a 3-year, $12.75M contract",
        now, "signing", entity_ids=entities,
    )
    assert cid1 == cid2


def test_role_headline_bridge_needs_evidence_beyond_the_name(pg_db):
    """Deliberate, documented regression from CM-2 — see brief 15.

    The entity-free version of this scenario
    (test_role_headline_merges_with_named_sibling_via_summary) still merges,
    because stripping nothing leaves headline overlap behind. Once the subject
    is a known entity, these two share *only* the name — which is structurally
    identical to the bad pairs above, so no lexical rule can keep them apart.
    Splitting is the accepted trade under brief 14's governing principle;
    story_key (brief 15) is what restores the merge.
    """
    src = _source(pg_db)
    now = datetime.utcnow()
    entities = [
        _entity(pg_db, "Keaton Verhoeff").id,
        _entity(pg_db, "San Jose Sharks", "team").id,
    ]
    cid1 = _cluster(
        pg_db, src,
        "San Jose Sharks prospect Keaton Verhoeff to return to North Dakota",
        now, "prospect", llm_summary="Keaton Verhoeff returns to North Dakota",
        entity_ids=entities,
    )
    cid2 = _cluster(
        pg_db, src,
        "San Jose Sharks' first round draft pick finalizes plans for upcoming season",
        now, "prospect", llm_summary="Keaton Verhoeff finalizes upcoming season plans",
        entity_ids=entities,
    )
    assert cid1 != cid2


def test_cluster_stops_accepting_variants_once_its_story_is_old(pg_db):
    """CM-5: the window follows the cluster's own clock, not its traffic.

    Under the old last_seen_at anchor every join renewed the lease, so a busy
    cluster never aged out — production held one spanning 435 hours against a
    72-hour window.
    """
    src = _source(pg_db)
    t0 = datetime.utcnow() - timedelta(hours=200)
    title = "Sharks sign Libor Hajek to a one year contract"

    cid1 = _cluster(pg_db, src, title, t0, "signing")
    # 60h later: inside the 72h window, joins, and pushes last_seen_at forward.
    cid2 = _cluster(pg_db, src, title, t0 + timedelta(hours=60), "signing")
    assert cid1 == cid2

    # 120h after the story broke. last_seen_at is only 60h old, so the old
    # filter still offered this cluster as a candidate; first_seen_at does not.
    cid3 = _cluster(pg_db, src, title, t0 + timedelta(hours=120), "signing")
    assert cid3 != cid1
