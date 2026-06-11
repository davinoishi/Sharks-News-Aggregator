"""Auth, trusted-proxy, and rate-limit helpers (brief 07, Q3).

Extracted from ``app.main`` so the route modules in ``app.routers`` can depend
on them. Behaviour is unchanged from brief 01 (S1/S3).
"""
import hashlib
import ipaddress
import secrets
import threading
import time
from typing import Optional

from fastapi import Header, HTTPException, Request

from app.core.config import settings


def hash_client_ip(ip: Optional[str]) -> str:
    """Return a salted SHA-256 hash of a client IP for privacy-preserving storage.

    Raw IPs are never persisted; the salted hash is deterministic so rate-limit
    comparisons still work. Set IP_HASH_SALT in the environment so the hashes
    aren't trivially reversible via a rainbow table of the IP space.
    """
    salt = settings.ip_hash_salt or ""
    return hashlib.sha256(f"{salt}:{ip or ''}".encode("utf-8")).hexdigest()


def require_admin(
    x_admin_api_key: Optional[str] = Header(default=None, alias="X-Admin-API-Key"),
):
    """FastAPI dependency enforcing admin auth via the X-Admin-API-Key header.

    Fail-closed: if ``settings.admin_api_key`` is empty/unset, every admin
    request is denied. There is no IP-based fallback — behind the Next.js proxy
    the backend only ever sees the proxy/tunnel IP. The 403 body intentionally
    contains no request detail.
    """
    configured = settings.admin_api_key or ""
    provided = x_admin_api_key or ""
    if not configured or not secrets.compare_digest(provided, configured):
        raise HTTPException(status_code=403, detail="Admin access denied")
    return True


def _parse_trusted_networks():
    nets = []
    for part in settings.trusted_proxy_ips.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return nets


def get_real_client_ip(request: Request) -> str:
    """Return the real client IP.

    Honors ``X-Forwarded-For`` only when the direct peer is a configured trusted
    proxy (the Next.js container on the Docker bridge); otherwise returns the
    direct peer IP. This stops clients from spoofing their IP with a forged
    header while still recovering the real IP from our own proxy.
    """
    direct_peer = request.client.host if request.client else ""
    try:
        peer_obj = ipaddress.ip_address(direct_peer)
    except ValueError:
        return direct_peer

    for net in _parse_trusted_networks():
        if peer_obj in net:
            xff = request.headers.get("X-Forwarded-For")
            if xff:
                # Leftmost entry is the original client.
                candidate = xff.split(",")[0].strip()
                if candidate:
                    return candidate
            break
    return direct_peer


# In-memory fixed-window limiter for public counter endpoints.
# NOTE: this is per-process state. With multiple uvicorn workers each worker
# keeps its own buckets, so the effective limit is roughly N * the configured
# value. That's acceptable here — the goal is stopping trivial counter spam,
# not precise enforcement. Back this with Redis if you need a strict global cap.
_METRICS_WINDOW_SECONDS = 60
_metrics_buckets: dict = {}  # client_ip -> [window_index, count]
_metrics_lock = threading.Lock()


def enforce_metrics_rate_limit(request: Request):
    """Cheap per-client rate limit for /metrics/pageview and cluster clicks."""
    client_ip = get_real_client_ip(request) or "unknown"
    limit = settings.metrics_rate_limit_per_min
    window = int(time.time()) // _METRICS_WINDOW_SECONDS

    with _metrics_lock:
        bucket = _metrics_buckets.get(client_ip)
        if bucket is None or bucket[0] != window:
            bucket = [window, 0]
        bucket[1] += 1
        _metrics_buckets[client_ip] = bucket
        count = bucket[1]
        # Opportunistic cleanup so the dict can't grow unbounded.
        if len(_metrics_buckets) > 10000:
            _metrics_buckets.clear()

    if count > limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
