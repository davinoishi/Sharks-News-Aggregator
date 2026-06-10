"""Tests for the SSRF URL guard (brief 02, S2)."""
import socket

import httpx
import pytest

from app.core import url_guard
from app.core.url_guard import UrlNotAllowed, validate_url, fetch_guarded


def _mock_dns(monkeypatch, mapping):
    """Patch socket.getaddrinfo so hostnames resolve to controlled IPs."""
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror(f"unknown host {host}")
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))
            for ip in mapping[host]
        ]
    monkeypatch.setattr(url_guard.socket, "getaddrinfo", fake_getaddrinfo)


# --- blocked IP literals (no DNS needed) -------------------------------------

@pytest.mark.parametrize("url", [
    "http://10.0.0.1/",
    "http://192.168.1.10/",
    "http://172.16.5.4/",
    "http://127.0.0.1/",
    "http://localhost:6379/",            # resolves to loopback
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata, link-local
    "http://[::1]/",                     # IPv6 loopback
    "http://[fd00::1]/",                 # IPv6 unique-local
    "http://[::ffff:10.0.0.1]/",         # IPv4-mapped IPv6 private
    "http://0.0.0.0/",                   # unspecified
])
def test_blocked_addresses(url):
    with pytest.raises(UrlNotAllowed):
        validate_url(url)


# --- scheme / port / credentials ---------------------------------------------

@pytest.mark.parametrize("url", [
    "ftp://example.com/",
    "file:///etc/passwd",
    "gopher://example.com/",
])
def test_bad_scheme(url):
    with pytest.raises(UrlNotAllowed):
        validate_url(url)


def test_credentials_in_url_rejected(monkeypatch):
    _mock_dns(monkeypatch, {"example.com": ["93.184.216.34"]})
    with pytest.raises(UrlNotAllowed):
        validate_url("http://user:pass@example.com/")


def test_nonstandard_port_rejected(monkeypatch):
    _mock_dns(monkeypatch, {"example.com": ["93.184.216.34"]})
    with pytest.raises(UrlNotAllowed):
        validate_url("http://example.com:8080/")


def test_custom_allowed_ports(monkeypatch):
    _mock_dns(monkeypatch, {"example.com": ["93.184.216.34"]})
    assert validate_url("http://example.com:8080/", allowed_ports={8080}).startswith("http")


# --- hostnames via mocked DNS ------------------------------------------------

def test_internal_hostname_rejected(monkeypatch):
    _mock_dns(monkeypatch, {"db": ["172.18.0.2"]})
    with pytest.raises(UrlNotAllowed):
        validate_url("http://db:5432/")


def test_public_hostname_allowed(monkeypatch):
    _mock_dns(monkeypatch, {"example.com": ["93.184.216.34"]})
    assert validate_url("https://example.com/article") == "https://example.com/article"


def test_public_ip_literal_allowed():
    assert validate_url("https://93.184.216.34/") == "https://93.184.216.34/"


def test_rejects_when_any_resolved_addr_is_private(monkeypatch):
    # Mixed public + private => reject (rebinding/round-robin safety).
    _mock_dns(monkeypatch, {"evil.test": ["93.184.216.34", "10.0.0.5"]})
    with pytest.raises(UrlNotAllowed):
        validate_url("https://evil.test/")


def test_unresolvable_host_rejected(monkeypatch):
    _mock_dns(monkeypatch, {})
    with pytest.raises(UrlNotAllowed):
        validate_url("https://nope.invalid/")


# --- redirect handling via httpx.MockTransport -------------------------------

def test_redirect_to_private_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        # First (public) hop redirects to an internal address.
        return httpx.Response(302, headers={"location": "http://10.0.0.1/"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    with pytest.raises(UrlNotAllowed):
        fetch_guarded("https://93.184.216.34/", client=client)


def test_oversize_response_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1024)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    with pytest.raises(UrlNotAllowed):
        fetch_guarded("https://93.184.216.34/", max_bytes=100, client=client)


def test_successful_fetch_returns_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hello world")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    resp = fetch_guarded("https://93.184.216.34/", client=client)
    assert resp.status_code == 200
    assert resp.text == "hello world"


def test_gzip_response_is_decoded_once():
    # Regression: fetch_guarded must not re-apply Content-Encoding to a body that
    # httpx already decoded — otherwise gzip'd pages raise "incorrect header check".
    import gzip

    original = "héllo gzip wörld" * 50
    gzipped = gzip.compress(original.encode("utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip", "Content-Type": "text/html; charset=utf-8"},
            content=gzipped,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    resp = fetch_guarded("https://93.184.216.34/", client=client)
    assert resp.status_code == 200
    # Body reads back as the decoded text, and the stale encoding header is gone.
    assert resp.text == original
    assert "content-encoding" not in resp.headers
