"""Optional WebPageEnrichmentProvider.

Fetches a property URL ONLY when every condition is met:

* page enrichment is explicitly enabled (``PAGE_ENRICHMENT_ENABLED=true``)
* the source/domain is allowed by configuration
* automated access is permitted by the source policy
* robots/access rules are respected (the fetcher does not bypass CAPTCHA,
  authentication, paywalls, bot protection or rate limits)
* the URL passes the strict SSRF guard (http/https only, no internal/private
  network, no localhost, no metadata endpoints)

Page fetching is OFF the hot path: when disabled (the default), the system
works entirely from search-provider metadata.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.discovery.sources import get_source_by_domain
from app.providers.web_search.security import assert_safe_for_fetch

logger = logging.getLogger(__name__)

_MAX_BYTES = 500_000  # 500 KB cap — bounded responses only
_MAX_REDIRECTS = 3


class WebPageEnrichmentProvider:
    """Bounded, policy-gated HTML page fetcher (returns structured metadata)."""

    name = "web_page_enrichment"

    def __init__(self, client: Optional[httpx.Client] = None) -> None:
        self._client = client

    def _http_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            timeout=httpx.Timeout(settings.WEB_SEARCH_TIMEOUT_SECONDS),
            follow_redirects=True,
            max_redirects=_MAX_REDIRECTS,
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT, "Accept": "text/html"},
        )

    def can_fetch(self, url: str) -> tuple[bool, str]:
        """Return (allowed, reason). Never silently bypasses restrictions."""
        if not settings.PAGE_ENRICHMENT_ENABLED:
            return False, "Page enrichment is disabled (PAGE_ENRICHMENT_ENABLED=false)."
        if not url:
            return False, "missing url"
        from urllib.parse import urlparse

        domain = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if settings.web_search_allowed_domains and not any(
            domain == entry or domain.endswith("." + entry)
            for entry in settings.web_search_allowed_domains
        ):
            return False, "domain not in WEB_SEARCH_ALLOWED_DOMAINS"
        source = get_source_by_domain(domain)
        if source is not None and not source.page_fetch_allowed:
            return False, f"{source.name} does not permit automated page fetching."
        try:
            assert_safe_for_fetch(url)
        except Exception as exc:  # noqa: BLE001 - security guard
            return False, str(exc)
        return True, "allowed"

    def fetch(self, url: str) -> Optional[dict[str, Any]]:
        """Fetch and return normalized page metadata, or None when not allowed.

        Never returns raw page text that could carry prompt-injection content
        into the AI layer; only small, bounded metadata fields are returned.
        """
        allowed, reason = self.can_fetch(url)
        if not allowed:
            logger.info("page_fetch_blocked url=%s reason=%s", url[:120], reason)
            return None
        try:
            with self._http_client() as client:
                response = client.get(url)
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPError) as exc:
            logger.warning("page_fetch_failed url=%s error=%s", url[:120], exc)
            return None
        if response.status_code != 200:
            logger.info("page_fetch_status url=%s status=%s", url[:120], response.status_code)
            return None
        content_length = len(response.content or b"")
        if content_length > _MAX_BYTES:
            logger.info("page_fetch_oversized url=%s bytes=%s", url[:120], content_length)
            return None
        return self._extract_safe_metadata(response)

    @staticmethod
    def _extract_safe_metadata(response: httpx.Response) -> dict[str, Any]:
        """Extract only safe, bounded metadata. Page text is untrusted data that
        must NEVER reach the AI layer as instructions."""
        html = (response.text or "")[:_MAX_BYTES]
        title = _extract_tag(html, "title")
        description = _extract_meta(html, "description")
        og_title = _extract_meta(html, "og:title")
        robots = _extract_meta(html, "robots")
        return {
            "page_title": (title or og_title or "")[:300],
            "description": description[:500] if description else None,
            "robots_meta": robots[:200] if robots else None,
            "content_type": response.headers.get("content-type", "")[:100],
            "length_bytes": len(html),
        }


def _extract_tag(html: str, tag: str) -> Optional[str]:
    import re

    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return _strip_tags(match.group(1))[:300]


def _extract_meta(html: str, name: str) -> Optional[str]:
    import re

    match = re.search(
        rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    )
    if not match:
        match = re.search(
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:name|property)=["\']{re.escape(name)}["\']',
            html, re.IGNORECASE,
        )
    if not match:
        return None
    return _strip_tags(match.group(1))[:500]


def _strip_tags(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()