"""SECURITY tests for web discovery: dangerous URL schemes, SSRF targets,
localhost, private IP literals, credentials in URLs, allowlist behavior and the
DNS-resolving fetch guard.
"""
from __future__ import annotations

import pytest

from app.providers.web_search.models import WebSearchInvalidRequestError
from app.providers.web_search.security import (
    assert_safe_for_fetch,
    is_allowed_domain,
    validate_result_url,
)


def test_allowed_url_is_normalized():
    assert validate_result_url("https://www.example.com/property/a?x=1#section") == (
        "https://www.example.com/property/a?x=1"
    )
    assert validate_result_url("http://example.com") == "http://example.com/"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(document.cookie)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "mailto:user@example.com",
        "//example.com/path",
        "https://user:pass@example.com/x",
        "https://exa mple.com/x",
        "https://example.com:99999/x",
    ],
)
def test_dangerous_urls_are_blocked(url):
    with pytest.raises(WebSearchInvalidRequestError):
        validate_result_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://10.0.0.1/x",
        "http://192.168.1.5/x",
        "http://172.16.0.5/x",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0/x",
        "http://localhost:8000/x",
        "http://[::1]/x",
        "https://metadata.google.internal/x",
    ],
)
def test_ssrf_targets_are_blocked(url):
    with pytest.raises(WebSearchInvalidRequestError):
        validate_result_url(url)


def test_fetch_guard_resolves_and_blocks_private_hosts(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, proto=socket.IPPROTO_TCP: [("AF_INET", "SOCK_STREAM", 6, "", ("10.0.0.5", port))],
    )
    with pytest.raises(WebSearchInvalidRequestError) as excinfo:
        assert_safe_for_fetch("https://internal.example.com/x")
    assert "internal/private" in str(excinfo.value)


def test_fetch_guard_accepts_public_hosts(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, proto=socket.IPPROTO_TCP: [("AF_INET", "SOCK_STREAM", 6, "", ("93.184.216.34", port))],
    )
    assert assert_safe_for_fetch("https://example.com/path") == "https://example.com/path"


def test_fetch_guard_rejects_non_http():
    with pytest.raises(WebSearchInvalidRequestError):
        assert_safe_for_fetch("file:///etc/passwd")


def test_domain_allowlist_behavior():
    assert is_allowed_domain("exampleportal.com", []) is True
    assert is_allowed_domain("exampleportal.com", ["exampleportal.com"]) is True
    assert is_allowed_domain("www.exampleportal.com", ["exampleportal.com"]) is True
    assert is_allowed_domain("otherportal.com", ["exampleportal.com"]) is False
    # The allowlist permits subdomains of an allowed domain by design.
    assert is_allowed_domain("news.exampleportal.com", ["exampleportal.com"]) is True