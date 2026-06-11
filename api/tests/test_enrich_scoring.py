"""Tests for the clustering decision logic — pure scoring functions (brief 06).

These cover the merge/no-merge gate and the per-signal scores that
``match_or_create_cluster`` composes, including threshold boundaries.
"""
from datetime import datetime, timedelta

import pytest

from app.core.config import settings
from app.tasks.enrich import (
    classify_event_type_keyword,
    count_event_keyword_matches,
    entity_overlap_score,
    event_compatibility_score,
    extract_game_identifier,
    get_time_window_for_event,
    is_match,
    jaccard_similarity,
    normalize_title_for_matching,
    title_similarity,
)

# --- entity_overlap_score ----------------------------------------------------

def test_entity_overlap_basic():
    assert entity_overlap_score([1, 2, 3], [2, 3, 4]) == pytest.approx(2 / 3)


def test_entity_overlap_empty_is_zero():
    assert entity_overlap_score([], [1]) == 0.0
    assert entity_overlap_score([1], []) == 0.0


def test_entity_overlap_uses_max_denominator():
    # One shared entity out of a big cluster → small score (prevents roster matches).
    assert entity_overlap_score([1], [1, 2, 3, 4, 5]) == pytest.approx(1 / 5)


# --- jaccard_similarity ------------------------------------------------------

def test_jaccard_basic():
    assert jaccard_similarity(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)


def test_jaccard_identical():
    assert jaccard_similarity(["a", "b"], ["a", "b"]) == 1.0


def test_jaccard_empty():
    assert jaccard_similarity([], ["a"]) == 0.0


# --- event_compatibility_score ----------------------------------------------

def test_event_exact_match():
    assert event_compatibility_score("game", "game") == 1.0


def test_event_compatible_pair():
    assert event_compatibility_score("trade", "signing") == 0.5


def test_event_incompatible():
    assert event_compatibility_score("game", "injury") == 0.0


# --- get_time_window_for_event ----------------------------------------------

@pytest.mark.parametrize("event,hours", [
    ("game", 24), ("opinion", 48), ("trade", 72), ("injury", 72), ("unknown", 72),
])
def test_time_window(event, hours):
    assert get_time_window_for_event(event) == timedelta(hours=hours)


# --- is_match (the merge gate + threshold boundaries) ------------------------

def test_match_when_entity_and_score_gates_pass():
    assert is_match(E=0.6, T=0.5, S=0.7, entities_v=[1, 2]) is True


def test_no_match_below_score_threshold():
    assert is_match(E=0.6, T=0.5, S=0.5, entities_v=[1, 2]) is False


def test_no_match_below_entity_threshold():
    assert is_match(E=0.3, T=0.5, S=0.7, entities_v=[1, 2]) is False


def test_no_entities_uses_token_gate():
    assert is_match(E=0.0, T=0.5, S=0.7, entities_v=[]) is True
    assert is_match(E=0.0, T=0.3, S=0.7, entities_v=[]) is False


def test_llm_override_bypasses_entity_gate():
    assert is_match(E=0.1, T=0.1, S=0.7, entities_v=[1], L=0.75) is True


def test_score_threshold_boundary():
    thr = settings.cluster_similarity_threshold  # 0.62
    assert is_match(E=0.6, T=0.5, S=thr, entities_v=[1]) is True
    assert is_match(E=0.6, T=0.5, S=thr - 0.001, entities_v=[1]) is False


def test_entity_threshold_boundary():
    thr = settings.entity_overlap_threshold  # 0.50
    assert is_match(E=thr, T=0.0, S=0.7, entities_v=[1]) is True
    assert is_match(E=thr - 0.001, T=0.0, S=0.7, entities_v=[1]) is False


# --- title / game-id matching ------------------------------------------------

def test_title_similarity_identical():
    assert title_similarity("celebrini signs", "celebrini signs") == 1.0


def test_title_similarity_empty():
    assert title_similarity("", "x") == 0.0


def test_normalize_title_lowercases_and_strips_punctuation():
    assert normalize_title_for_matching("Celebrini, Signs!") == "celebrini signs"


@pytest.mark.xfail(
    reason="BUG: normalize_title_for_matching lowercases before a regex that "
    "looks for capitalized publication names, so the suffix is never stripped",
    strict=True,
)
def test_normalize_title_strips_publication_suffix():
    assert normalize_title_for_matching("Farabee scores winner - Western Wheel") == (
        "farabee scores winner"
    )


def test_extract_game_identifier_with_opponent():
    dt = datetime(2026, 1, 15, 19, 0, 0)
    assert extract_game_identifier("Sharks beat Boston in OT", dt) == "BOS-2026-01-15"


def test_extract_game_identifier_none_without_opponent():
    assert extract_game_identifier("Sharks sign a prospect", datetime(2026, 1, 15)) is None


# --- keyword event classification --------------------------------------------

def test_classify_trade():
    assert classify_event_type_keyword("Sharks trade Karlsson to Pittsburgh", []) == "trade"


def test_classify_other_when_no_keywords():
    assert classify_event_type_keyword("zzz qqq wxyz", []) == "other"


def test_count_event_keyword_matches_only_positive():
    scores = count_event_keyword_matches("sharks sign a contract extension")
    assert scores.get("signing", 0) >= 2
    assert "injury" not in scores
