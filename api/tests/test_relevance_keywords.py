"""Tests for the tiered Sharks keyword check and the wrong-sport veto (RM-3).

Both cover one prod incident: "Longstaff agrees to new deal with Sharks -
Yahoo Sport", a Sale Sharks *rugby union* story that reached the feed because
the bare word "sharks" was, on its own, sufficient for relevance. At least four
pro clubs carry the name, and the Google Alerts source queries the bare word.

Production runs LLM_EVALUATION_MODE=true, so the keyword check is the decision
maker and the LLM's (correct) rejection was only logged — which is why these
tests exercise check_sharks_relevance directly.
"""
from types import SimpleNamespace

import pytest

from app.enrichment.classify import (
    check_sharks_relevance,
    has_hockey_context,
    is_wrong_sport,
)


class _StubDB:
    """Stands in for a Session: check_sharks_relevance only ever asks which of
    the given entity ids are non-team entities."""

    def __init__(self, non_team_ids=()):
        self.non_team_ids = set(non_team_ids)

    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def all(self):
        return [SimpleNamespace(id=i) for i in sorted(self.non_team_ids)]


def relevant(title, url="", entity_ids=(), non_team_ids=(), source_is_hockey=False):
    return check_sharks_relevance(
        _StubDB(non_team_ids), title, list(entity_ids), url, source_is_hockey
    )


# --- the incident ------------------------------------------------------------

def test_rugby_sharks_story_is_rejected():
    assert not relevant(
        "Longstaff agrees to new deal with Sharks - Yahoo Sport",
        url="https://uk.sports.yahoo.com/news/longstaff-agrees-new-deal-sharks.html",
    )


def test_rugby_story_rejected_even_with_a_rugby_section_url_alone():
    # The title carries no disqualifying word — the URL path is the only signal.
    assert not relevant(
        "Sharks confirm squad for the new season",
        url="https://www.skysports.com/rugby-union/news/12345/sharks-squad",
    )


def test_rugby_veto_outranks_an_entity_match():
    # A surname collision must not rescue a rugby story.
    assert not relevant(
        "Sale Sharks sign Smith on a two-year deal",
        entity_ids=[7],
        non_team_ids=[7],
    )


# --- strong keywords approve alone -------------------------------------------

@pytest.mark.parametrize("title", [
    "San Jose Sharks acquire defenseman in blockbuster",
    "SJ Sharks fall in overtime",
    "Barracuda recall forward from ECHL",
])
def test_strong_keyword_approves_without_corroboration(title):
    assert relevant(title)


# --- weak keywords need corroboration ----------------------------------------

def test_bare_sharks_with_hockey_vocabulary_is_kept():
    assert relevant("Sharks recall goaltender ahead of road trip")


def test_bare_sharks_with_san_jose_in_the_title_is_kept():
    assert relevant("Longstaff agrees to new deal in San Jose with the Sharks")


def test_bare_sharks_with_san_jose_in_the_url_is_kept():
    assert relevant(
        "Sharks agree to terms with veteran forward",
        url="https://www.nbcsports.com/san-jose/sharks/veteran-forward-deal",
    )


def test_bare_sharks_from_a_hockey_scoped_source_is_kept():
    # League-wide hockey outlets run headlines naming neither the city nor a
    # roster player. The source flag is what stands in for the missing signal.
    assert relevant("Sharks and Kraken swap picks", source_is_hockey=True)


def test_bare_sharks_with_no_hockey_signal_is_rejected():
    assert not relevant("Sharks announce new commercial partnership")


# Real headlines from the 741-item snapshot that a narrower corroboration list
# rejected. None carries hockey vocabulary, a roster player, or the city name —
# the NHL opponent name or the publisher's URL is the only thing marking them
# as hockey, which is why both are corroborating signals.

@pytest.mark.parametrize("title,url", [
    ("Rangers at Sharks game 50: Lines, game thread and how to watch - Fear the Fin", ""),
    ("Lineup Notes: Lekkerimäki Gets Top Six Opportunity As Canucks Face The Sharks", ""),
    ("Rangers' loss to Sharks the latest example of costly starts to games", ""),
    ("Hamilton Blocked A Trade To Sharks In Summer",
     "https://www.prohockeyrumors.com/2026/01/snapshots-hamilton-smith.html"),
    ("Sharks' Roster Crunch Hits Critical Mass & Potential Landing Spot for Elias Pettersson?",
     "https://thehockeywriters.substack.com/p/sharks-roster-crunch-hits-critical"),
])
def test_real_sharks_stories_survive_the_weak_keyword_gate(title, url):
    assert relevant(title, url=url)


def test_known_loss_a_headline_with_no_hockey_token_anywhere():
    # Snapshot item 546. Genuine Sharks content, rejected: the title has no
    # hockey word, no opponent and no city, and sports.yahoo.com/videos/ says
    # nothing about the sport. Documented rather than fixed — the only way to
    # admit it is to accept bare 'Sharks', which is the hole RM-3 closes.
    assert not relevant(
        "Sharks Have Big Decision To Make With Important Defender - Yahoo Sports",
        url="https://sports.yahoo.com/videos/sharks-big-decision-important-defender-010931935.html",
    )


def test_nhl_opponent_does_not_rescue_a_rugby_story():
    # The wrong-sport veto runs first, so an NRL side sharing a name with an
    # NHL one ("Panthers") can't corroborate.
    assert not relevant("Cronulla Sharks upset the Panthers")


def test_entity_match_still_approves_without_any_keyword():
    # RM-2's gate, deliberately unchanged by RM-3.
    assert relevant("Celebrini named to the all-star roster", entity_ids=[3], non_team_ids=[3])


def test_team_only_entity_does_not_corroborate_a_weak_keyword():
    # entity id 9 is present but is a team entity, so it isn't a second signal.
    assert not relevant("Sharks announce ticket pricing", entity_ids=[9], non_team_ids=[])


# --- the two RM-2 false positives this also retires ---------------------------

def test_non_hockey_event_at_sap_center_is_rejected():
    assert not relevant("AEW Forbidden Door Explodes at SAP Center")


def test_sap_center_with_hockey_context_is_kept():
    assert relevant("Sharks beat Kings at SAP Center behind goalie's 40 saves")


def test_hashtag_only_description_is_rejected():
    assert not relevant("Teal just hits different. 🔥 #sharks")


def test_hashtag_chrome_naming_the_league_is_kept():
    # '#nhl' is a real hockey signal even in hashtag soup — corroborated, kept.
    assert relevant("Teal just hits different. 🔥 #sharks #nhl #hockey")


# --- no signal at all ---------------------------------------------------------

def test_unrelated_article_is_rejected():
    assert not relevant("Edmonton police to introduce involuntary detention detox")


# --- is_wrong_sport -----------------------------------------------------------

@pytest.mark.parametrize("title", [
    "Sharks name new rugby director",
    "Cronulla Sharks upset the Panthers",
    "Natal Sharks through to the Currie Cup final",
    "Sharks scrum-half ruled out for six weeks",
    "Super Rugby: Sharks host the Stormers",
])
def test_wrong_sport_titles(title):
    assert is_wrong_sport(title)


@pytest.mark.parametrize("title", [
    "Sharks acquire Nurse from Edmonton",
    "Sharks winger scores in overtime",
    "Macklin Celebrini signs extension",
])
def test_hockey_titles_are_not_wrong_sport(title):
    assert not is_wrong_sport(title)


def test_wrong_sport_url_segments():
    assert is_wrong_sport("Sharks squad news", "https://example.com/rugby-league/sharks")
    assert is_wrong_sport("Sharks squad news", "https://example.com/nrl/2026/round-4")
    assert not is_wrong_sport("Sharks squad news", "https://example.com/nhl/san-jose")


def test_wrong_sport_tolerates_missing_input():
    assert not is_wrong_sport("", "")
    assert not is_wrong_sport(None, None)


def test_ambiguous_words_are_not_treated_as_wrong_sport():
    # 'try', 'league' and 'union' all appear in ordinary hockey coverage, so
    # none of them may trigger the veto.
    assert not is_wrong_sport("Sharks try to shake off a rough road trip")
    assert not is_wrong_sport("NHL and the players' union agree on a new deal")
    assert not is_wrong_sport("Sharks prospect dominates junior league play")


# --- has_hockey_context -------------------------------------------------------

def test_hockey_context_requires_a_real_signal():
    assert has_hockey_context("Sharks recall a defenseman")
    assert has_hockey_context("Sharks news", url="https://example.com/san-jose/sharks")
    assert has_hockey_context("Anything at all", source_is_hockey=True)
    assert not has_hockey_context("Sharks announce partnership")
