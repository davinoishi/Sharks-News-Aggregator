"""Tests for URL normalization / dedup keying (brief 06, ingest.normalize_url)."""
import pytest

from app.tasks.ingest import normalize_url


@pytest.mark.parametrize("param", [
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref", "fbclid",
])
def test_strips_tracking_params(param):
    out = normalize_url(f"https://example.com/article?{param}=x")
    assert param not in out
    assert out.startswith("https://example.com/article")


def test_keeps_meaningful_params():
    out = normalize_url("https://example.com/a?id=5&page=2")
    assert "id=5" in out
    assert "page=2" in out


def test_mixed_tracking_and_real_params():
    out = normalize_url("https://example.com/a?id=5&utm_source=tw&fbclid=abc")
    assert "id=5" in out
    assert "utm_source" not in out
    assert "fbclid" not in out


def test_removes_fragment():
    assert normalize_url("https://example.com/a#section") == "https://example.com/a"


def test_no_query_unchanged():
    assert normalize_url("https://example.com/path") == "https://example.com/path"


def test_preserves_path_and_host():
    out = normalize_url("https://Sub.Example.com/deep/path/")
    assert "Sub.Example.com" in out
    assert "/deep/path/" in out


def test_unwraps_google_redirect():
    inner = "https://realsite.com/story"
    out = normalize_url(f"https://www.google.com/url?rct=j&url={inner}&usg=x")
    assert out == "https://realsite.com/story"


def test_unwraps_google_redirect_and_strips_inner_tracking():
    out = normalize_url(
        "https://www.google.com/url?url=https://realsite.com/story%3Futm_source%3Dgoogle%26id%3D9"
    )
    assert out.startswith("https://realsite.com/story")
    assert "utm_source" not in out
    assert "id=9" in out


def test_google_redirect_without_url_param_is_not_unwrapped():
    out = normalize_url("https://www.google.com/url?q=somethingelse")
    assert out.startswith("https://www.google.com/url")


def test_idempotent():
    once = normalize_url("https://example.com/a?utm_source=x&id=5#frag")
    assert normalize_url(once) == once


def test_fragment_and_tracking_together():
    out = normalize_url("https://example.com/a?utm_campaign=c#top")
    assert "#" not in out
    assert "utm_campaign" not in out
