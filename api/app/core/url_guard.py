"""SSRF protection for user-supplied URLs.

This module validates URLs *before* any server-side fetch so the submissions
worker cannot be tricked into probing internal services (Redis, Postgres, the
Pi's LAN, cloud metadata endpoints at 169.254.169.254, etc.).

What it blocks:
- non-http(s) schemes, credentials-in-URL (``user:pass@host``), and ports
  outside the configured allowlist (80/443 by default);
- hostnames that resolve to *any* private / loopback / link-local / multicast /
  reserved / unspecified / non-global address, including raw IPv4/IPv6
  literals and IPv4-mapped IPv6 (``::ffff:10.0.0.1``).

DNS-rebinding stance
--------------------
``fetch_guarded`` re-resolves and re-validates the host immediately before each
request and validates every redirect hop (capped). It does **not** pin the
socket to the validated IP, so a sub-second DNS flip between our resolution and
httpx's own resolution is theoretically possible. Full IP-pinning (connecting to
the resolved address while preserving SNI/Host for TLS) is recorded as a future
hardening; re-resolve-and-validate is the chosen, documented minimum per the
project brief and keeps TLS verification correct.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Iterable, Optional
from urllib.parse import urlsplit

import httpx

from app.core.config import settings


class UrlNotAllowed(Exception):
    """Raised when a URL fails SSRF validation. Messages are for logs only."""


_ALLOWED_SCHEMES = {"http", "https"}
_DEFAULT_PORT_BY_SCHEME = {"http": 80, "https": 443}


def _allowed_ports(explicit: Optional[Iterable[int]] = None) -> set:
    if explicit is not None:
        return set(explicit)
    ports = set()
    for part in str(settings.submission_allowed_ports).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ports.add(int(part))
        except ValueError:
            continue
    return ports or {80, 443}


def _normalize_ip(ip_str: str) -> ipaddress._BaseAddress:
    """Parse an IP and unwrap IPv4-mapped IPv6 so range checks aren't bypassed."""
    obj = ipaddress.ip_address(ip_str)
    if isinstance(obj, ipaddress.IPv6Address) and obj.ipv4_mapped is not None:
        return obj.ipv4_mapped
    return obj


def _is_blocked_ip(obj: ipaddress._BaseAddress) -> bool:
    return (
        obj.is_private
        or obj.is_loopback
        or obj.is_link_local
        or obj.is_multicast
        or obj.is_reserved
        or obj.is_unspecified
        or not obj.is_global
    )


def _resolve_addresses(host: str, port: int) -> list:
    """Return all IPs ``host`` resolves to. Raises UrlNotAllowed on failure."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlNotAllowed(f"could not resolve host: {host}") from exc
    addrs = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr and sockaddr[0]:
            addrs.append(sockaddr[0])
    if not addrs:
        raise UrlNotAllowed(f"no addresses for host: {host}")
    return addrs


def validate_url(url: str, *, allowed_ports: Optional[Iterable[int]] = None) -> str:
    """Validate ``url`` for SSRF safety.

    Returns the URL unchanged on success; raises :class:`UrlNotAllowed`
    otherwise. Performs DNS resolution and rejects if *any* resolved address is
    in a blocked range.
    """
    if not url or not isinstance(url, str):
        raise UrlNotAllowed("empty url")

    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UrlNotAllowed(f"scheme not allowed: {scheme!r}")

    if parts.username or parts.password:
        raise UrlNotAllowed("credentials in URL are not allowed")

    host = parts.hostname
    if not host:
        raise UrlNotAllowed("missing host")

    try:
        port = parts.port if parts.port is not None else _DEFAULT_PORT_BY_SCHEME[scheme]
    except ValueError as exc:
        raise UrlNotAllowed("invalid port") from exc
    if port not in _allowed_ports(allowed_ports):
        raise UrlNotAllowed(f"port not allowed: {port}")

    # Raw IP literal? Check it directly (no DNS).
    try:
        literal = _normalize_ip(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked_ip(literal):
            raise UrlNotAllowed(f"blocked address: {host}")
        return url

    # Hostname: resolve and validate every address it maps to.
    for addr in _resolve_addresses(host, port):
        if _is_blocked_ip(_normalize_ip(addr)):
            raise UrlNotAllowed(f"host resolves to blocked address: {host}")

    return url


def fetch_guarded(
    url: str,
    *,
    method: str = "GET",
    timeout: Optional[float] = None,
    max_bytes: Optional[int] = None,
    max_redirects: Optional[int] = None,
    allowed_ports: Optional[Iterable[int]] = None,
    client: Optional[httpx.Client] = None,
) -> httpx.Response:
    """Fetch ``url`` with SSRF validation on every hop and a response size cap.

    Redirects are followed manually (auto-redirects disabled) so each hop is
    re-validated. Raises :class:`UrlNotAllowed` on a blocked URL/hop, too many
    redirects, or an over-size body.
    """
    timeout = settings.request_timeout_seconds if timeout is None else timeout
    max_bytes = settings.submission_fetch_max_bytes if max_bytes is None else max_bytes
    max_redirects = (
        settings.submission_max_redirects if max_redirects is None else max_redirects
    )

    owns_client = client is None
    if owns_client:
        client = httpx.Client(follow_redirects=False, timeout=timeout)

    try:
        current = url
        for _ in range(max_redirects + 1):
            # Re-resolve & validate immediately before each request.
            validate_url(current, allowed_ports=allowed_ports)

            with client.stream(method, current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        resp.read()
                        return resp
                    current = str(resp.url.join(location))
                    continue

                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise UrlNotAllowed("response exceeds size cap")

                return httpx.Response(
                    status_code=resp.status_code,
                    headers=resp.headers,
                    content=bytes(body),
                    request=resp.request,
                )

        raise UrlNotAllowed("too many redirects")
    finally:
        if owns_client:
            client.close()
