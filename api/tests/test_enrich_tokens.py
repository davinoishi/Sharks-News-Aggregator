"""Tests for normalize_tokens (brief 06). Needs NLTK corpora (ensured in conftest)."""
from app.tasks.enrich import extract_person_name_keys, normalize_tokens


def test_lowercases_and_keeps_content_words():
    tokens = normalize_tokens("The Sharks signed Celebrini!")
    assert "sharks" in tokens
    assert "signed" in tokens
    assert "celebrini" in tokens


def test_removes_stopwords():
    tokens = normalize_tokens("the and of a to in")
    assert tokens == []


def test_drops_short_tokens_and_punctuation():
    tokens = normalize_tokens("a in to Karlsson, traded!!!")
    assert "karlsson" in tokens
    assert "traded" in tokens
    assert all(len(t) > 2 for t in tokens)
    assert all("," not in t and "!" not in t for t in tokens)


def test_empty_text():
    assert normalize_tokens("") == []


def test_general_manager_canonicalized_to_gm():
    tokens = normalize_tokens("Sharks Hire Jeff Kealty as Assistant General Manager")
    assert "gm" in tokens
    assert "general" not in tokens
    assert "manager" not in tokens


def test_gm_survives_short_token_filter():
    assert "gm" in normalize_tokens("Sharks hire new assistant GM")


# --- extract_person_name_keys ------------------------------------------------

def test_name_keys_finds_person_bigram():
    assert extract_person_name_keys(
        "Sharks Hire Jeff Kealty as Assistant General Manager"
    ) == {"jeff kealty"}
    assert "jeff kealty" in extract_person_name_keys(
        "Assistant GM Jeff Kealty departs Predators to pursue position with Sharks - Predlines"
    )


def test_name_keys_ignores_teams_and_headline_words():
    assert extract_person_name_keys(
        "Florida Panthers vs. San Jose Sharks Live Updates"
    ) == set()
    assert extract_person_name_keys("Sharks Hire New Assistant GM") == set()


def test_name_keys_empty_title():
    assert extract_person_name_keys("") == set()
