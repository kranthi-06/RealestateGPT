"""Licensed/approved property data provider contracts.

Only legitimate, authorized sources may be adapted. No scraping of third-party
listing sites is implemented or planned. Every adapter must normalize raw
records into the canonical provider-record shape (see ``ProviderRecord``) so the
ingestion pipeline can validate them independently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple


@dataclass
class ProviderRecord:
    """A raw record as delivered by an adapter, before ingestion validation.

    This is intentionally loose: adapters map their source's native shape into
    these fields and the ingestion pipeline strictly validates the result.
    """

    source_listing_id: str
    title: str
    price: float
    property_type: str
    city: str
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self.raw)
        data.update(
            {
                "source_listing_id": self.source_listing_id,
                "title": self.title,
                "price": self.price,
                "property_type": self.property_type,
                "city": self.city,
            }
        )
        return data


class PropertyProvider(Protocol):
    """Contract every property adapter implements.

    ``fetch_properties`` drives the ingestion worker with cursor-based
    pagination. ``search``/``get_property``/``refresh`` support the UI and the
    listing-refresh worker.
    """

    name: str
    source_type: str

    async def search(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]: ...

    async def get_property(self, source_listing_id: str) -> Dict[str, Any]: ...

    async def refresh(self, source_listing_id: str) -> Dict[str, Any]: ...

    async def fetch_properties(
        self, cursor: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]: ...