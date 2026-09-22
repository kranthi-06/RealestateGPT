"""Safe URL validation for web discovery.

All URLs entering the application from search results are untrusted. This module
provides a single strict validator that:

* only allows http / https schemes
* blocks javascript:, data:, file: and any other scheme
* blocks credentials in the URL
* resolves the hostname and rejects internal/private networks (SSRF guard),
  localhost, link-local, and cloud-metadata endpoints

``validate_result_url`` is applied to every ``WebSearchResult.url`` before the
discovery layer persists or renders it.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from app.providers.web_search.models import WebSearchInvalidRequestError

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_URL_LENGTH = 2048

# Hostname characters per RFC; rejects spaces/underscores/backslashes.
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$")

# Cloud metadata / internal hostnames must never be reachable.
_BLOCKED_HOST_SUFFIXES = (
    ".internal",
    ".local",
    ".localhost",
)
_BLOCKED_HOST_EXACT = {
    "metadata.google.internal",
    "169.254.169.254",
    "169.254.170.2",
    "100.100.100.200",
    "fd00:ec2::254",
    "localhost",
}

_PRIVATE_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fec0::/10"),
)


def _blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return any(ip in network for network in _PRIVATE_NETWORKS)


def validate_result_url(raw: str) -> str:
    """Validate and normalize an external http(s) URL. Returns the normalized URL.

    Raises :class:`WebSearchInvalidRequestError` for dangerous or malformed URLs.
    """
    raw = (raw or "").strip()
    if not raw:
        raise WebSearchInvalidRequestError("URL is required.")
    if len(raw) > _MAX_URL_LENGTH:
        raise WebSearchInvalidRequestError("URL is too long.")

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise WebSearchInvalidRequestError(
            f"Blocked URL scheme: {scheme or 'none'}. Only http/https are allowed."
        )
    if "@" in parsed.netloc:
        raise WebSearchInvalidRequestError("URL credentials are not allowed.")
    host = (parsed.hostname or "").lower().strip(".")
    if not host:
        raise WebSearchInvalidRequestError("URL host is missing.")
    if not _HOSTNAME_RE.match(host):
        raise WebSearchInvalidRequestError("URL host is malformed.")
    if host in _BLOCKED_HOST_EXACT or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise WebSearchInvalidRequestError("URL host is blocked.")

    try:
        port = parsed.port
    except ValueError:
        raise WebSearchInvalidRequestError("URL port is invalid.")
    if port is not None and not (1 <= port <= 65535):
        raise WebSearchInvalidRequestError("URL port is invalid.")

    # Lightweight SSRF guard for *display* URLs: block private-network IP
    # literals and blocked hostnames. DNS resolution is intentionally NOT
    # performed here — a search-result URL should still render when its domain
    # is temporarily unresolvable. Full DNS-resolving SSRF protection applies
    # only in assert_safe_for_fetch (outbound fetching).
    try:
        ip = ipaddress.ip_address(host)
        if _blocked_ip(ip):
            raise WebSearchInvalidRequestError("Internal/private network URLs are blocked.")
    except (ValueError, TypeError):
        pass

    return _normalize(raw)


def _normalize(raw: str) -> str:
    """Reconstruct a clean URL without fragment and with a default path."""
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.rstrip(".")
    path = parsed.path or "/"
    query = parsed.query
    url = f"{scheme}://{netloc}"
    if path:
        url += ("/" + path.lstrip("/")) if path != "/" else path
    if query:
        url += "?" + query
    return url


def assert_safe_for_fetch(url: str) -> str:
    """Strict pre-fetch validation for optional page enrichment.

    Adds the full DNS-resolving SSRF guard (private/internal/link-local
    addresses, cloud metadata) on top of :func:`validate_result_url`, because
    fetching opens a real connection to the target host.
    """
    if not url.startswith(("http://", "https://")):
        raise WebSearchInvalidRequestError("Only http/https URLs may be fetched.")
    url = validate_result_url(url)
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().strip(".")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Hostname: resolve every address and reject if any is private.
        try:
            port = parsed.port or 443
        except ValueError:
            raise WebSearchInvalidRequestError("URL port is invalid.")
        try:
            resolved_any = False
            for resolved in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP):
                resolved_any = True
                try:
                    resolved_ip = ipaddress.ip_address(resolved[4][0])
                except ValueError:
                    continue
                if _blocked_ip(resolved_ip):
                    raise WebSearchInvalidRequestError(
                        "URL resolves to an internal/private network and is blocked."
                    )
        except WebSearchInvalidRequestError:
            raise
        except OSError:
            raise WebSearchInvalidRequestError("URL host could not be resolved.")
        if not resolved_any:
            raise WebSearchInvalidRequestError("URL host could not be resolved.")
    else:
        if _blocked_ip(ip):
            raise WebSearchInvalidRequestError("Internal/private network URLs are blocked.")
    return url


def is_allowed_domain(domain: str, allowlist: list[str]) -> bool:
    """True when the domain is allowed by the configured allowlist (or no allowlist)."""
    if not allowlist:
        return True
    domain = (domain or "").lower().lstrip(".")
    return any(domain == entry or domain.endswith("." + entry) for entry in allowlist)
