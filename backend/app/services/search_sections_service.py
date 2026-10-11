"""Adaptive, inventory-driven search sections.

Every section is produced by running a real MongoDB query; sections with zero
matches are omitted. Natural-language intent from ``parse_query`` is layered
over the explicit filters. Proximity sections ("Near Metro", "Near You") are
built from real OSM geocoding of the requested place and real geo queries.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.ai.query_parser import parse_query
from app.schemas import SearchSection
from app.services.property_service import PropertyService

logger = logging.getLogger(__name__)

_ALLOWED = {
    "city", "locality", "property_type", "listing_type", "min_price",
    "max_price", "bedrooms", "bathrooms", "min_bedrooms", "max_bedrooms",
    "min_area", "max_area", "furnishing", "amenities", "construction_status",
    "parking", "floor", "min_floor", "max_floor", "latitude", "longitude",
    "radius_km", "exclude_id", "sort_by", "sort_order",
}

_BHK_BUCKETS = (1, 2, 3, 4)
_TYPE_BUCKETS = (
    ("apartment", "Apartments"),
    ("villa", "Villas"),
    ("plot", "Plots & Land"),
    ("independent_house", "Independent Houses"),
    ("studio", "Studios"),
    ("penthouse", "Penthouses"),
)


class SearchSectionsService:
    def __init__(self, db) -> None:
        self.db = db
        self.service = PropertyService(db)
        self._user_id: Optional[int] = None

    def build_sections(self, params: Dict[str, Any], user_id: Optional[int] = None):
        from concurrent.futures import ThreadPoolExecutor

        self._user_id = user_id
        base = self._merge_intent({k: v for k, v in params.items() if v not in (None, "")})
        intent = parse_query(params["q"]) if (params.get("q") or "").strip() else None

        # Build list of planned section specs in display order
        specs: list[tuple[str, str, dict[str, Any]]] = [
            ("best_matches", "Best Matches", {}),
        ]

        if intent and intent.max_price and not base.get("min_price"):
            specs.append(("under_budget", "Under Budget", {"max_price": intent.max_price, "min_price": None}))
        if intent and intent.min_price:
            specs.append(("premium", "Premium Options", {"min_price": intent.min_price, "max_price": None}))

        if not any(base.get(key) is not None for key in ("bedrooms", "min_bedrooms", "max_bedrooms")):
            for bhk in _BHK_BUCKETS:
                specs.append(("bhk_" + str(bhk), str(bhk) + " BHK", {"bedrooms": bhk}))

        if not base.get("property_type"):
            for ptype, label in _TYPE_BUCKETS:
                specs.append((ptype, label, {"property_type": ptype}))

        if not base.get("listing_type"):
            specs.append(("for_rent", "For Rent", {"listing_type": "rent"}))
            specs.append(("for_sale", "For Sale", {"listing_type": "sale"}))

        coord_lat, coord_lon = base.get("latitude"), base.get("longitude")
        if coord_lat is not None and coord_lon is not None:
            specs.append(("near_me", "Near You", {"radius_km": float(params.get("radius_km") or 5.0)}))

        if intent and intent.nearby_requirements and coord_lat is None:
            for req in intent.nearby_requirements[:3]:
                coords = self._geocode_place(req, base)
                if coords is not None:
                    title = "Near " + req.type.replace("_", " ").title()
                    specs.append((
                        "near_" + req.type, title,
                        {"latitude": coords[0], "longitude": coords[1], "radius_km": min(req.max_distance_km, 10)},
                    ))

        # Query all sections in parallel via thread pool (I/O bound DB queries)
        with ThreadPoolExecutor(max_workers=min(8, len(specs) or 1)) as executor:
            futures = [
                executor.submit(self._fetch_section, base, sid, title, extra)
                for sid, title, extra in specs
            ]
            sections = []
            for f in futures:
                sec = f.result()
                if sec is not None:
                    sections.append(sec)

        return {"sections": sections}

    def _merge_intent(self, base: Dict[str, Any]) -> Dict[str, Any]:
        q = base.get("q")
        if not q:
            return base
        intent = parse_query(q)
        merged = dict(base)
        for key in (
            "city", "locality", "property_type", "bedrooms", "bathrooms",
            "min_price", "max_price", "min_area", "max_area", "furnishing",
        ):
            value = getattr(intent, key, None)
            if value not in (None, "") and merged.get(key) in (None, ""):
                merged[key] = value
        if not merged.get("listing_type") and intent.listing_type:
            merged["listing_type"] = intent.listing_type
        return merged

    def _fetch_section(self, base: Dict[str, Any], section_id: str, title: str, extra: Dict[str, Any], limit: int = 4) -> Optional[SearchSection]:
        filters = {k: v for k, v in base.items() if k in _ALLOWED and v not in (None, "")}
        filters.pop("q", None)
        filters.update(extra)
        filters.setdefault("sort_by", "created_at")
        filters.setdefault("sort_order", "desc")

        try:
            resp = self.service.search_properties(user_id=self._user_id, page=1, page_size=limit, **filters)
        except Exception as exc:
            logger.warning("section_query_failed section=%s error=%s", section_id, exc)
            return None
        total = resp.total if resp else 0
        if total > 0:
            from app.schemas import PropertyCardResponse

            items = [PropertyCardResponse.model_validate(prop) for prop in resp.properties]
            return SearchSection(
                id=section_id,
                title=title,
                count=total,
                items=items,
                next_cursor="2" if total > len(items) else None,
            )
        return None

    def _add(self, sections, base: Dict[str, Any], section_id: str, title: str, extra: Dict[str, Any], limit: int = 4) -> int:
        sec = self._fetch_section(base, section_id, title, extra, limit)
        if sec is not None:
            sections.append(sec)
            return sec.count
        return 0

    def _geocode_place(self, req, base: Dict[str, Any]) -> Optional[tuple[float, float]]:
        """Real OSM geocoding of 'place category near <city>' — never fabricated."""
        try:
            from app.providers.location import LocationProviderUnavailable, get_location_provider

            city = base.get("city")
            query = req.type.replace("_", " ").title()
            if city:
                query = query + ", " + str(city)
            provider = get_location_provider()
            result = provider.geocode(query)
            lat = result.get("latitude")
            lon = result.get("longitude")
            if lat is None or lon is None:
                return None
            return float(lat), float(lon)
        except (LocationProviderUnavailable, Exception) as exc:
            logger.warning("section_geocode_failed place=%s error=%s", req.type, exc)
            return None