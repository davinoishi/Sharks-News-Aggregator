"""Endpoint-level check that /submit/link enforces the SSRF guard (brief 02)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_submit_private_url_rejected_with_generic_message():
    # Blocked before any DB write / Celery enqueue, so no DB is needed.
    resp = client.post("/submit/link", json={"url": "http://10.0.0.1/"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "URL not allowed"


def test_submit_metadata_endpoint_rejected():
    resp = client.post("/submit/link", json={"url": "http://169.254.169.254/"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "URL not allowed"
