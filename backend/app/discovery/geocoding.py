"""Bounded geocoding/OSM enrichment for web discoveries.

Rules
-----
* Only enrich the top ``WEB_DISCOVERY_OSM_ENRICH_LIMIT`` discoveries per run.
* Geocode ``location_text`` via the configured LocationProvider (Nominatim/OSM)
  with the existing rate limits and geocode_cache — never fabricate coordinates.
* If geocoding fails, keep ``location_text`` and leave coordinates null.
* OSM "nearby" enrichment is intentionally NOT performed per card here; the
  discovery pipeline depends only on direct geocoding so search stays fast.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.providers.location import (
    LocationProviderUnavailable,
    get_location_provider,
)
from app.discovery.repository import WebDiscoveryRepository, _utcnow

logger = logging.getLogger(__name__)

# The existing geocoding worker treats 1.5s as a safe floor; this is confidence
# leftover for turbolent public nominatim instances. We read from settings.
_MIN_INTERVAL_SECONDS = 1.0


class DiscoveryGeocoder:
    def __init__(self, db, limit: int = 10) -> None:
        self.db = db
        self.limit = limit
        self.repo = WebDiscoveryRepository(db)

    def enrich(self, doc_ids: list[str]) -> dict[str, Any]:
        """Geocode the first ``limit`` discoveries with a location_text.

        Returns a summary dict: {attempted, geocoded, failed, skipped}.
        Never raises: provider failures are recorded and skipped.
        """
        attempted = geocoded = failed = skipped = 0
        try:
            provider = get_location_provider()
        except Exception as exc:  # noqa: BLE001 - provider misconfiguration
            logger.warning("discovery_geocode_provider_unavailable error=%s", exc)
            return {"attempted": 0, "geocoded": 0, "failed": 0, "skipped": len(doc_ids)}

        candidates: list[str] = []
        for discovery_id in doc_ids:
            doc = self.repo.by_id(discovery_id)
            if not doc:
                continue
            address = (doc.get("location_text") or "").strip()
            if not address:
                skipped += 1
                continue
            if doc.get("latitude") is not None and doc.get("longitude") is not None:
                skipped += 1
                continue
            candidates.append(discovery_id)

        for discovery_id in candidates[: self.limit]:
            doc = self.repo.by_id(discovery_id)
            if not doc:
                continue
            address = (doc.get("location_text") or "").strip()
            attempted += 1
            try:
                cached = _cache_lookup(address)
                if cached:
                    self.repo.update_coordinates(
                        doc["_id"], cached[0], cached[1], cached[2]
                    )
                    geocoded += 1
                    continue
                result = provider.geocode(address)
                lat, lon = result.get("latitude"), result.get("longitude")
                if lat is None or lon is None:
                    failed += 1
                    continue
                _cache_store(address, lat, lon, provider.name)
                self.repo.update_coordinates(doc["_id"], lat, lon, provider.name)
                geocoded += 1
            except LocationProviderUnavailable as exc:
                logger.warning("discovery_geocode_failed address=%r error=%s", address, exc)
                failed += 1
                break  # provider down: stop throttling it further
            except Exception as exc:  # noqa: BLE001 - defensive
                logger.warning("discovery_geocode_error address=%r error=%s", address, exc)
                failed += 1
        return {"attempted": attempted, "geocoded": geocoded, "failed": failed, "skipped": skipped}


_cache: dict[str, tuple[float, float, str]] = {}


def _cache_lookup(address: str) -> Optional[tuple[float, float, str]]:
    cached = _cache.get(address.casefold())
    return cached


def _cache_store(address: str, latitude: float, longitude: float, provider: str) -> None:
    _cache[address.casefold()] = (latitude, longitude, provider)