"""Tests for the OpenRouter service parsing + fail-open behavior (brief 06).

All network calls are mocked by monkeypatching ``_call_chat`` — tests run offline.
"""
import pytest

from app.services.openrouter import OpenRouterService


@pytest.fixture
def svc():
    return OpenRouterService(api_key="test-key")


# --- _parse_json_content: the three extraction paths + failure ---------------

def test_parse_plain_json(svc):
    parsed, err = svc._parse_json_content('{"relevant": true}')
    assert err is None and parsed == {"relevant": True}


def test_parse_markdown_fenced_json(svc):
    parsed, err = svc._parse_json_content('```json\n{"event_type": "trade"}\n```')
    assert err is None and parsed == {"event_type": "trade"}


def test_parse_embedded_json(svc):
    parsed, err = svc._parse_json_content('Sure! {"relevant": false} hope that helps')
    assert err is None and parsed == {"relevant": False}


def test_parse_unparseable_returns_error(svc):
    parsed, err = svc._parse_json_content("no json here at all")
    assert parsed is None and err is not None


# --- check_relevance ---------------------------------------------------------

def test_check_relevance_fails_open_on_error(svc, monkeypatch):
    monkeypatch.setattr(svc, "_call_chat", lambda *a, **k: (None, "boom"))
    result = svc.check_relevance("Some title")
    assert result.is_relevant is True       # fail-open
    assert result.error == "boom"


def test_check_relevance_respects_false(svc, monkeypatch):
    monkeypatch.setattr(
        svc, "_call_chat", lambda *a, **k: ({"relevant": False, "confidence": "HIGH"}, None)
    )
    result = svc.check_relevance("Some title")
    assert result.is_relevant is False
    assert result.error is None


def test_check_relevance_defaults_true_when_key_missing(svc, monkeypatch):
    monkeypatch.setattr(svc, "_call_chat", lambda *a, **k: ({"confidence": "LOW"}, None))
    assert svc.check_relevance("t").is_relevant is True


# --- classify_and_summarize: validation against allowed sets -----------------

def test_classify_filters_invalid_tags_and_events(svc, monkeypatch):
    monkeypatch.setattr(
        svc,
        "_call_chat",
        lambda *a, **k: (
            {"tags": ["Trade", "NotARealTag"], "event_type": "trade", "summary": "x"},
            None,
        ),
    )
    result = svc.classify_and_summarize("title")
    assert result.tags == ["Trade"]
    assert result.event_type == "trade"


def test_classify_coerces_unknown_event_to_other(svc, monkeypatch):
    monkeypatch.setattr(
        svc, "_call_chat", lambda *a, **k: ({"tags": [], "event_type": "zzz"}, None)
    )
    assert svc.classify_and_summarize("title").event_type == "other"


def test_classify_error_propagates(svc, monkeypatch):
    monkeypatch.setattr(svc, "_call_chat", lambda *a, **k: (None, "timeout"))
    result = svc.classify_and_summarize("title")
    assert result.error == "timeout"
    assert result.event_type == "other"


def test_classify_parses_low_value_flag(svc, monkeypatch):
    monkeypatch.setattr(
        svc,
        "_call_chat",
        lambda *a, **k: (
            {"tags": ["Game"], "event_type": "game", "summary": "x", "low_value": True},
            None,
        ),
    )
    assert svc.classify_and_summarize("Watch Stars vs Sharks - Fubo").low_value is True


def test_classify_low_value_accepts_string_and_defaults_false(svc, monkeypatch):
    monkeypatch.setattr(
        svc, "_call_chat",
        lambda *a, **k: ({"tags": [], "event_type": "game", "low_value": "true"}, None),
    )
    assert svc.classify_and_summarize("title").low_value is True

    # Absent flag (older prompt / partial response) must fail open to False.
    monkeypatch.setattr(
        svc, "_call_chat", lambda *a, **k: ({"tags": [], "event_type": "game"}, None)
    )
    assert svc.classify_and_summarize("title").low_value is False


def test_classify_low_value_false_on_error(svc, monkeypatch):
    monkeypatch.setattr(svc, "_call_chat", lambda *a, **k: (None, "timeout"))
    assert svc.classify_and_summarize("title").low_value is False


# --- brief 15: story_key -----------------------------------------------------

def test_normalize_story_key_coerces_model_output():
    from app.services.openrouter import normalize_story_key

    assert normalize_story_key("Celebrini-Rookie-Card-Auction") == "celebrini-rookie-card-auction"
    assert normalize_story_key("  celebrini rookie card  ") == "celebrini-rookie-card"
    assert normalize_story_key("CELEBRINI--CARD!!") == "celebrini-card"
    assert normalize_story_key("a" * 200) == "a" * 80


def test_normalize_story_key_returns_none_rather_than_a_fragment():
    """A garbage key is strictly worse than no key.

    The matcher reads absent as "no information" and present as evidence, so
    salvaging something unusable would turn a model slip into a false veto.
    """
    from app.services.openrouter import normalize_story_key

    for junk in (None, "", "   ", "!!!", "-----", 123, [], {}):
        assert normalize_story_key(junk) is None


def test_story_key_verdict_is_three_valued():
    from app.enrichment.clustering import story_key_verdict

    # Near-misses for the same event agree; equality would lose this.
    assert story_key_verdict(
        "celebrini-rookie-card-auction", "celebrini-card-auction"
    )[0] == "agree"
    # Same person, different events — the case no lexical measure separates.
    assert story_key_verdict(
        "celebrini-rookie-card-auction", "celebrini-contract-extension"
    )[0] == "differ"
    # Missing on either side is "no information", never a mismatch.
    assert story_key_verdict("celebrini-rookie-card-auction", None)[0] == "unknown"
    assert story_key_verdict(None, None)[0] == "unknown"
