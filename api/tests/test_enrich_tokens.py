"""Tests for normalize_tokens (brief 06). Needs NLTK corpora (ensured in conftest)."""
from app.tasks.enrich import normalize_tokens


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
