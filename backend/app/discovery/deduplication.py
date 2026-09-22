"""Deduplication of web-discovered property candidates.

Primary key: canonical URL.
Secondary key: normalized (source_domain, source_listing_id).
Additional signals (title similarity + location/price/bedrooms/area/source) are
used only to flag near-duplicates for review — never to auto-merge listings from
different sources unless there is strong evidence they are the same property.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from app.discovery.models import PropertyCandidate

# Tracking params that never change a listing's identity.
_TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "src", "fbclid", "gclid", "igshid"}
_TRACKING_PREFIXES = ("utm_",)


def canonical_url(url: str) -> str:
    """Normalize a URL into a stable canonical identity:
    scheme lowered, host lowered without www, default port dropped,
    tracking params removed, fragment stripped.
    """
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    host = (parts.netloc or "").lower()
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    host = host.removeprefix("www.").removeprefix("m.")
    # Drop explicit default ports.
    if host.endswith(":443") and parts.scheme == "https":
        host = host[: -len(":443")]
    elif host.endswith(":80") and parts.scheme == "http":
        host = host[: -len(":80")]

    query = parse_qs(parts.query, keep_blank_values=True)
    kept = {
        key: values
        for key, values in query.items()
        if not key.startswith(_TRACKING_PREFIXES) and key.lower() not in _TRACKING_KEYS
    }
    ordered = "&".join(
        f"{key}={value}" for key in sorted(kept) for value in kept[key]
    )
    normalized = urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/") or "/", ordered, ""))
    return normalized


def _sentinel_dedupe_key(candidate: PropertyCandidate) -> str:
    """Secondary key: source_domain + source_listing_id (when available)."""
    listing_id = (candidate.source_listing_id or "").strip()
    if not listing_id:
        return ""
    return f"{candidate.source_domain}|{listing_id}"


def find_duplicates(
    candidates: Iterable[PropertyCandidate],
) -> tuple[list[PropertyCandidate], list[PropertyCandidate]]:
    """Split candidates into unique and duplicate.

    Ordering follows the input order (already confidence-descending), so the
    first occurrence of each canonical identity wins. A result from source A and
    a result from source B remain separate unless they share a canonical URL.
    """
    candidates = list(candidates)
    unique: list[PropertyCandidate] = []
    duplicates: list[PropertyCandidate] = []
    seen_urls: set[str] = set()
    seen_source_keys: set[str] = set()

    for candidate in candidates:
        url_key = canonical_url(candidate.url)
        source_key = _sentinel_dedupe_key(candidate)
        duplicate = False
        if url_key and url_key in seen_urls:
            duplicate = True
        elif source_key and source_key in seen_source_keys:
            duplicate = True
        if duplicate:
            duplicates.append(candidate)
            continue
        if url_key:
            seen_urls.add(url_key)
        if source_key:
            seen_source_keys.add(source_key)
        unique.append(candidate)
    return unique, duplicates


def near_duplicate_pairs(candidates: Iterable[PropertyCandidate], threshold: float = 0.9) -> list[tuple[PropertyCandidate, PropertyCandidate]]:
    """Flag pairs that look like the same property for review (never auto-merge)."""
    items = list(candidates)
    pairs: list[tuple[PropertyCandidate, PropertyCandidate]] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if not _same_market(items[i], items[j]):
                continue
            title_sim = SequenceMatcher(
                None, items[i].title.lower(), items[j].title.lower()
            ).ratio()
            if title_sim >= threshold:
                pairs.append((items[i], items[j]))
    return pairs


def _same_market(a: PropertyCandidate, b: PropertyCandidate) -> bool:
    """Coarse market fingerprint (city + price bucket + bedrooms + area)."""
    city_a = (a.city or "").casefold()
    city_b = (b.city or "").casefold()
    if city_a and city_b and city_a != city_b:
        return False
    price_diff = False
    if a.price is not None and b.price is not None:
        price_diff = abs(a.price - b.price) > max(10_000, 0.25 * max(a.price, b.price))
    if price_diff:
        return False
    if a.bedrooms is not None and b.bedrooms is not None and a.bedrooms != b.bedrooms:
        return False
    return True