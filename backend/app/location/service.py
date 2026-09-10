"""RealEstateGPT - Location intelligence service.

Maps providers are abstracted (OsmProvider stub etc.); distance math is
deterministic haversine. Nearby POIs are stored in the database so business
logic never depends on a third-party provider at runtime.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.platform import NearbyPlace

PLACE_CATEGORIES = {
    "metro": "transport",
    "transport": "transport",
    "airport": "transport",
    "hospital": "healthcare",
    "school": "education",
    "college": "education",
    "supermarket": "retail",
    "mall": "retail",
    "park": "recreation",
    "it_park": "work",
}

CATEGORY_LABELS = {
    "metro": "Metro", "transport": "Public transport", "airport": "Airport",
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
    """Rough drive-time estimate for illustration (city-average speeds)."""
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
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_property(self, property_id: int, city: Optional[str] = None) -> List[NearbyPlace]:
        query = self.db.query(NearbyPlace)
        if city:
            query = query.filter(NearbyPlace.city.ilike(f"%{city}%"))
        places = query.all()
        prop = None
        if property_id:
            from app.models.property import Property
            prop = self.db.query(Property).filter(Property.id == property_id).first()
        if prop and prop.latitude and prop.longitude:
            return places
        # Property without coordinates still returns all seeds for the city (distances omitted).
        return places

    def nearby(self, property_id: int, place_type: str, radius_km: float = 3.0) -> List[dict]:
        prop = self._property(property_id)
        if not prop or not prop.latitude or not prop.longitude:
            return []
        rows = (
            self.db.query(NearbyPlace)
            .filter(
                NearbyPlace.place_type == place_type,
                NearbyPlace.city.ilike(f"%{prop.city}%"),
            )
            .all()
        )
        results = []
        for place in rows:
            dist = haversine_km(prop.latitude, prop.longitude, place.latitude, place.longitude)
            if dist <= radius_km:
                results.append({
                    "id": place.id,
                    "name": place.name,
                    "place_type": place.place_type,
                    "category": place.category,
                    "locality": place.locality,
                    "city": place.city,
                    "distance_km": dist,
                    "estimated_drive_min": estimate_drive_min(dist, place.place_type),
                })
        results.sort(key=lambda r: r["distance_km"])
        return results

    def nearby_by_type_map(self, property_id: int) -> Dict[str, float]:
        """Nearest distance per place type (for scoring connectivity)."""
        prop = self._property(property_id)
        result: Dict[str, float] = {}
        if not prop or not prop.latitude or not prop.longitude:
            return result
        rows = self.db.query(NearbyPlace).filter(NearbyPlace.city.ilike(f"%{prop.city}%")).all()
        for place in rows:
            dist = haversine_km(prop.latitude, prop.longitude, place.latitude, place.longitude)
            current = result.get(place.place_type)
            if current is None or dist < current:
                result[place.place_type] = round(dist, 3)
        return result

    def property_context(self, property_id: int) -> dict:
        """All categories with nearest distances for a property."""
        prop = self._property(property_id)
        if not prop:
            return {}
        nearby_map = self.nearby_by_type_map(property_id)
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

    def _property(self, property_id: int):
        from app.models.property import Property
        return self.db.query(Property).filter(Property.id == property_id).first()