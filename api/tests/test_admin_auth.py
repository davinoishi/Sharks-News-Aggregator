"""Tests for the proxy-aware admin auth dependency (brief 01, S1/S3)."""
import re

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app, require_admin, get_real_client_ip

client = TestClient(app)


# --- require_admin unit tests -------------------------------------------------

def test_require_admin_no_key_denies(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "s3cret")
    with pytest.raises(HTTPException) as exc:
        require_admin(None)
    assert exc.value.status_code == 403


def test_require_admin_wrong_key_denies(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "s3cret")
    with pytest.raises(HTTPException) as exc:
        require_admin("not-the-key")
    assert exc.value.status_code == 403


def test_require_admin_right_key_allows(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "s3cret")
    assert require_admin("s3cret") is True


def test_require_admin_empty_config_fails_closed(monkeypatch):
    # No configured key => deny everything, even a "matching" empty key.
    monkeypatch.setattr(settings, "admin_api_key", "")
    with pytest.raises(HTTPException) as exc:
        require_admin("")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        require_admin("anything")


# --- end-to-end via the router dependency ------------------------------------

def test_admin_route_denies_without_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "s3cret")
    resp = client.get("/admin/sources")
    assert resp.status_code == 403


def test_admin_403_body_leaks_no_ip(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "s3cret")
    resp = client.get("/admin/sources")
    assert resp.status_code == 403
    # 403 body must not echo any client IP or request detail.
    assert not re.search(r"\d{1,3}(?:\.\d{1,3}){3}", resp.text)


def test_admin_route_denies_when_unset(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "")
    resp = client.get("/admin/sources", headers={"X-Admin-API-Key": "anything"})
    assert resp.status_code == 403


# --- trusted-proxy IP resolution ---------------------------------------------

class _FakeRequest:
    def __init__(self, peer, headers=None):
        self.client = type("C", (), {"host": peer})()
        self.headers = headers or {}


def test_xff_honored_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_ips", "172.16.0.0/12")
    req = _FakeRequest("172.18.0.5", {"X-Forwarded-For": "203.0.113.7, 172.18.0.5"})
    assert get_real_client_ip(req) == "203.0.113.7"


def test_xff_ignored_from_untrusted_peer(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_ips", "172.16.0.0/12")
    # Direct peer is public => do not trust a forged XFF.
    req = _FakeRequest("203.0.113.99", {"X-Forwarded-For": "10.0.0.1"})
    assert get_real_client_ip(req) == "203.0.113.99"
