"""Contract for licensed or otherwise approved property-data feeds.

No provider implementation is bundled: scraping third-party listing sites is
explicitly out of scope. Implementations must be approved/licensed before they
are registered by application configuration.
"""
from __future__ import annotations

from typing import Any, Protocol, List


class PropertyProvider(Protocol):
    name: str
    source_type: str

    async def search(self, intent: dict[str, Any]) -> List[dict[str, Any]]: ...
    
    async def get_property(self, source_listing_id: str) -> dict[str, Any]: ...
    
    async def refresh(self, source_listing_id: str) -> dict[str, Any]: ...

    async def fetch_properties(self, cursor: str | None = None) -> tuple[List[dict[str, Any]], str | None]: ...


class ProviderNotConfiguredError(Exception):
    pass
