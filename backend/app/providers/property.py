"""Contract for licensed or otherwise approved property-data feeds.

No provider implementation is bundled: scraping third-party listing sites is
explicitly out of scope. Implementations must be approved/licensed before they
are registered by application configuration.
"""
from __future__ import annotations

from typing import Any, Protocol


class PropertyProvider(Protocol):
    name: str
    source_type: str

    def fetch_properties(self, cursor: str | None = None) -> tuple[list[dict[str, Any]], str | None]: ...
