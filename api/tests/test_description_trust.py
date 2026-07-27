"""Tests for per-source description trust and cluster headline selection.

Both cover one prod incident: a Google Alerts item titled "Edmonton police to
introduce involuntary detention detox" whose description was the publisher's
nav bar and "Trending" sidebar ("... San Jose Sharks won Darnell Nurse trade.
Trending ... News · Sports · Opinion ..."). That text produced a Darnell Nurse
entity, cleared relevance on that entity alone, was summarized as a Nurse trade
story, clustered with two genuine Nurse articles, and — having arrived first —
named the card.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.enrichment.clustering import _headline_sort_key, select_cluster_headline
from app.tasks.enrich import effective_description

# The real contaminated description, verbatim from raw_items 15243 on prod.
ALERTS_CHROME = (
    "... <b>San Jose Sharks</b> won Darnell Nurse trade. Trending. Hyman jets "
    "goal. Cult of Hockey ... <b>News</b> &middot; Sports &middot; Opinion "
    "&middot; Business &middot; Arts &middot; Life &middot; Lives Told&nbsp;..."
)


# --- effective_description ---------------------------------------------------

def test_description_dropped_for_flagged_source():
    assert effective_description({"description_unreliable": True}, ALERTS_CHROME) == ""


def test_description_kept_for_normal_source():
    # Bluesky mirrors and ordinary feeds must keep it — for the mirrors the
    # title is derived FROM the description, so dropping it blinds the source.
    assert effective_description({}, "Sharks recall Bordeleau") == "Sharks recall Bordeleau"
    assert effective_description(None, "Sharks recall Bordeleau") == "Sharks recall Bordeleau"


def test_description_flag_coexists_with_other_metadata():
    meta = {"skip_relevance_check": True, "description_unreliable": True}
    assert effective_description(meta, ALERTS_CHROME) == ""


def test_description_normalizes_missing_text_to_empty_string():
    assert effective_description({}, None) == ""
    assert effective_description({"description_unreliable": True}, None) == ""


# --- headline ranking --------------------------------------------------------

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
_SUMMARY = "Darnell Nurse trade to San Jose Sharks"


def _key(title, category="press", published_at=_NOW, summary=_SUMMARY):
    return _headline_sort_key(title, category, published_at, summary)


def test_headline_prefers_title_matching_the_cluster_subject():
    on_topic = _key("Darnell Nurse traded to the Sharks")
    off_topic = _key("Edmonton police to introduce involuntary detention detox")
    assert on_topic > off_topic


def test_headline_breaks_ties_on_source_authority():
    title = "Darnell Nurse traded to the Sharks"
    assert _key(title, category="official") > _key(title, category="press")
    assert _key(title, category="press") > _key(title, category="other")


def test_headline_breaks_remaining_ties_on_earliest_publication():
    # The original report should name the card, not a later rewrite of it.
    title = "Darnell Nurse traded to the Sharks"
    first = _key(title, published_at=_NOW)
    later = _key(title, published_at=_NOW + timedelta(hours=6))
    assert first > later


def test_headline_undated_variant_loses_the_tie_break():
    title = "Darnell Nurse traded to the Sharks"
    assert _key(title, published_at=_NOW) > _key(title, published_at=None)


def test_headline_ranking_without_a_summary_falls_back_to_source_and_date():
    # No LLM summary (LLM disabled or errored): every title scores 0 for
    # representativeness, so authority and recency decide rather than crashing.
    a = _headline_sort_key("Some title", "official", _NOW, None)
    b = _headline_sort_key("Another title", "press", _NOW, None)
    assert a > b


# --- select_cluster_headline -------------------------------------------------

class _StubQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return self.rows


class _StubDB:
    """Stands in for a Session: select_cluster_headline only ever reads back
    (title, published_at, category) rows for the cluster's members."""

    def __init__(self, rows):
        self.rows = rows

    def query(self, *a, **k):
        return _StubQuery(self.rows)


def _cluster(headline, summary=None):
    return SimpleNamespace(id=1, headline=headline, llm_summary=summary)


def test_select_headline_repicks_when_a_better_title_joins():
    cluster = _cluster("Edmonton police to introduce involuntary detention detox", _SUMMARY)
    db = _StubDB([("Edmonton police to introduce involuntary detention detox", _NOW, "press")])
    incoming = ("Darnell Nurse trade to San Jose Sharks reshapes the blue line", _NOW, "press")

    assert select_cluster_headline(db, cluster, incoming=incoming) == incoming[0]


def test_select_headline_keeps_incumbent_on_an_exact_tie():
    # summary_similarity strips publication suffixes, so these score identically.
    title = "Celebrini signs contract extension with Sharks"
    cluster = _cluster(title, "Celebrini contract extension")
    db = _StubDB([(title, _NOW, "press")])

    result = select_cluster_headline(
        db, cluster, incoming=(f"{title} - Yahoo Sports", _NOW, "press")
    )
    assert result == title


def test_select_headline_prefers_a_real_title_over_a_placeholder():
    cluster = _cluster("Untitled")
    db = _StubDB([("Untitled", _NOW, "press")])

    result = select_cluster_headline(
        db, cluster, incoming=("Sharks recall Bordeleau", _NOW, "other")
    )
    assert result == "Sharks recall Bordeleau"


def test_select_headline_returns_none_when_there_is_nothing_to_pick():
    # None means "keep the existing headline" rather than blanking the card.
    assert select_cluster_headline(_StubDB([]), _cluster("Something"), incoming=None) is None
