"""RealEstateGPT - Location intelligence service.

All live POIs come from the configured LocationProvider. The legacy
``nearby_places`` collection is not read by this service, so seeded records can
never be mixed with provider results.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from app.providers.location import get_location_provider
from app.repositories.property_repo import PropertyRepository

PLACE_CATEGORIES = {
    "metro": "transport",
    "hospital": "healthcare",
    "school": "education",
    "college": "education",
    "supermarket": "retail",
    "mall": "retail",
    "park": "recreation",
    "it_park": "work",
}

CATEGORY_LABELS = {
    "metro": "Metro",
    "hospital": "Hospital", "school": "School", "college": "College",
    "supermarket": "Supermarket", "mall": "Shopping", "park": "Park",
    "it_park": "IT Park",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 3)


def estimate_drive_min(distance_km: float, place_type: str = "") -> Optional[float]:
    """City-average drive-time estimate (clearly labeled as an estimate)."""
    if distance_km is None:
        return None
    if place_type == "airport":
        speed = 70.0
    elif place_type in ("metro", "transport"):
        speed = 35.0
    else:
        speed = 28.0
    return round(distance_km / speed * 60.0, 1)


class LocationService:
    def __init__(self, db) -> None:
        self.db = db
        self.properties_repo = PropertyRepository(db)
        self.provider = get_location_provider()

    def _property(self, property_id: int):
        return self.properties_repo.get_by_id(property_id, include_inactive=True)

    def list_for_property(self, property_id: int, city: Optional[str] = None) -> List[dict]:
        """Return only current provider POIs; ``city`` is retained for API compatibility."""
        prop = self._property(property_id) if property_id else None
        if not prop or prop.latitude is None or prop.longitude is None:
            return []
        places: List[dict] = []
        for place_type in CATEGORY_LABELS:
            places.extend(self.provider.nearby(prop.latitude, prop.longitude, place_type, 3.0))
        return sorted(places, key=lambda item: item.get("distance_km", float("inf")))

    def nearby(self, property_id: int, place_type: str, radius_km: float = 3.0) -> List[dict]:
        prop = self._property(property_id)
        if not prop or prop.latitude is None or prop.longitude is None:
            return []
        return self.provider.nearby(prop.latitude, prop.longitude, place_type, radius_km)

    def nearby_by_type_map(self, property_id: int) -> Dict[str, float]:
        """Nearest distance per place type (for scoring connectivity)."""
        prop = self._property(property_id)
        result: Dict[str, float] = {}
        if not prop or prop.latitude is None or prop.longitude is None:
            return result
        for place_type in CATEGORY_LABELS:
            places = self.provider.nearby(prop.latitude, prop.longitude, place_type, 5.0)
            if places and places[0].get("distance_km") is not None:
                result[place_type] = float(places[0]["distance_km"])
        return result

    def property_context(self, property_id: int) -> dict:
        """All categories with nearest distances for a property."""
        prop = self._property(property_id)
        if not prop:
            return {}
        categories = []
        all_places: List[dict] = []
        for ptype, label in CATEGORY_LABELS.items():
            within = self.nearby(property_id, ptype, radius_km=5.0)
            nearest = within[0] if within else None
            categories.append({
                "place_type": ptype,
                "count": len(within),
                "nearest_name": nearest["name"] if nearest else None,
                "nearest_distance_km": nearest["distance_km"] if nearest else None,
                "within_radius_count": len(within),
            })
            all_places.extend(within)
        all_places.sort(key=lambda r: r["distance_km"])
        return {
            "property_id": property_id,
            "latitude": prop.latitude,
            "longitude": prop.longitude,
            "city": prop.city,
            "locality": prop.locality,
            "categories": categories,
            "all_places": all_places[:40],
        }
