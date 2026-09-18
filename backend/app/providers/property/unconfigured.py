"""Sentinel provider used when no real provider is configured.

It never produces data. This is what makes the whole system honest: an empty
catalogue and clear UI messaging are preferable to invented inventory.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.providers.property.errors import ProviderNotConfiguredError


class UnconfiguredPropertyProvider:
    name = "not_configured"
    source_type = "none"

    async def search(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise ProviderNotConfiguredError(
            "No property provider is configured. Production inventory requires "
            "a licensed provider configuration."
        )

    async def get_property(self, source_listing_id: str) -> Dict[str, Any]:
        raise ProviderNotConfiguredError("No property provider is configured.")

    async def refresh(self, source_listing_id: str) -> Dict[str, Any]:
        raise ProviderNotConfiguredError("No property provider is configured.")

    async def fetch_properties(self, cursor: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        raise ProviderNotConfiguredError("No property provider is configured.")