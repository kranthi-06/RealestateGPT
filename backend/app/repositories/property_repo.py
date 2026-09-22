"""RealEstateGPT - Property repository (MongoDB).

All property queries are expressed as MongoDB filter/sort/aggregation
operations. Geospatial queries may be layered on ``location`` (2dsphere).
"""

import re
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from pymongo import ReturnDocument
from pymongo.database import Database

from app.core.database import next_id
from app.models.property import Property

_TEXTLIKE_FIELDS = [
    "title", "description", "locality", "city", "builder_name",
    "project_name", "address",
]


class PropertyRepository:
    NAME = "properties"

    def __init__(self, db: Database):
        self.db = db
        self.coll = db[self.NAME]

    # ─── Reads ──────────────────────────────────────────────────────────

    def get_by_id(self, property_id: int, include_inactive: bool = False) -> Optional[Property]:
        query: dict = {"_id": property_id}
        if not include_inactive:
            query["is_active"] = True
        return Property.from_doc(self.coll.find_one(query))

    def get_by_slug(self, slug: str) -> Optional[Property]:
        return Property.from_doc(
            self.coll.find_one({"slug": slug, "is_active": True})
        )

    def get_by_ids(
        self, property_ids: List[int], include_inactive: bool = False
    ) -> List[Property]:
        query: dict = {"_id": {"$in": property_ids}}
        if not include_inactive:
            query["is_active"] = True
        docs = self.coll.find(query)
        return [Property.from_doc(doc) for doc in docs if doc]

    def list_active(self, listing_type: Optional[str] = None, limit: Optional[int] = None) -> List[Property]:
        query: dict = {"is_active": True, "status": "active"}
        if listing_type:
            query["listing_type"] = listing_type
        cursor = self.coll.find(query)
        if limit:
            cursor = cursor.limit(limit)
        return [Property.from_doc(doc) for doc in cursor if doc]

    # ─── Search ─────────────────────────────────────────────────────────

    def search(
        self,
        q: Optional[str] = None,
        city: Optional[str] = None,
        locality: Optional[str] = None,
        property_type: Optional[str] = None,
        listing_type: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        bedrooms: Optional[int] = None,
        bathrooms: Optional[int] = None,
        min_bedrooms: Optional[int] = None,
        max_bedrooms: Optional[int] = None,
        min_area: Optional[float] = None,
        max_area: Optional[float] = None,
        furnishing: Optional[str] = None,
        amenities: Optional[List[str]] = None,
        parking: Optional[int] = None,
        floor: Optional[int] = None,
        min_floor: Optional[int] = None,
        max_floor: Optional[int] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        construction_status: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 12,
        exclude_id: Optional[int] = None,
    ) -> Tuple[List[Property], int]:
        """Filter + sort + paginate the property catalogue. Never trusts raw text."""
        query = self._build_search_query(
            q=q, city=city, locality=locality, property_type=property_type,
            listing_type=listing_type, min_price=min_price, max_price=max_price,
            bedrooms=bedrooms, min_bedrooms=min_bedrooms, max_bedrooms=max_bedrooms,
            bathrooms=bathrooms, min_area=min_area, max_area=max_area,
            furnishing=furnishing, amenities=amenities,
            parking=parking, floor=floor, min_floor=min_floor, max_floor=max_floor,
            latitude=latitude, longitude=longitude, radius_km=radius_km,
            construction_status=construction_status, exclude_id=exclude_id,
        )

        # MongoDB $near determines distance order and cannot be combined with a
        # separate sort. Count uses the equivalent geo-within circle.
        near_query = query.get("location", {}).get("$near")
        count_query = self._geo_count_query(query) if near_query else query
        total = self.coll.count_documents(count_query)
        cursor = self.coll.find(query)
        if not near_query:
            cursor = cursor.sort(sort_by, -1 if sort_order == "desc" else 1)
        cursor = cursor.skip((page - 1) * page_size).limit(page_size)
        return [Property.from_doc(doc) for doc in cursor if doc], total

    def _build_search_query(self, **filters: Any) -> dict:
        """Build a safe Mongo query from typed repository arguments only."""
        defaults = {
            "q": None, "city": None, "locality": None, "property_type": None,
            "listing_type": None, "min_price": None, "max_price": None,
            "bedrooms": None, "min_bedrooms": None, "max_bedrooms": None,
            "bathrooms": None, "min_area": None, "max_area": None,
            "furnishing": None, "amenities": None, "parking": None,
            "floor": None, "min_floor": None, "max_floor": None,
            "latitude": None,
            "longitude": None, "radius_km": None, "construction_status": None,
            "exclude_id": None,
        }
        filters = {**defaults, **filters}
        query: dict = {"is_active": True, "status": "active"}
        q, city, locality = filters["q"], filters["city"], filters["locality"]

        if q:
            pattern = re.escape(q)
            query["$or"] = [
                {field: {"$regex": pattern, "$options": "i"}}
                for field in _TEXTLIKE_FIELDS
            ]
        if city:
            query["city"] = {"$regex": re.escape(city), "$options": "i"}
        if locality:
            query["locality"] = {"$regex": re.escape(locality), "$options": "i"}
        if filters["property_type"]:
            query["property_type"] = filters["property_type"]
        if filters["listing_type"]:
            query["listing_type"] = filters["listing_type"]
        if filters["min_price"] is not None or filters["max_price"] is not None:
            price_range: dict = {}
            if filters["min_price"] is not None:
                price_range["$gte"] = filters["min_price"]
            if filters["max_price"] is not None:
                price_range["$lte"] = filters["max_price"]
            query["price"] = price_range
        if filters["bedrooms"] is not None:
            query["bedrooms"] = filters["bedrooms"]
        elif filters["min_bedrooms"] is not None or filters["max_bedrooms"] is not None:
            bedroom_range: dict = {}
            if filters["min_bedrooms"] is not None:
                bedroom_range["$gte"] = filters["min_bedrooms"]
            if filters["max_bedrooms"] is not None:
                bedroom_range["$lte"] = filters["max_bedrooms"]
            query["bedrooms"] = bedroom_range
        if filters["bathrooms"] is not None:
            query["bathrooms"] = filters["bathrooms"]
        if filters["min_area"] is not None or filters["max_area"] is not None:
            area_range: dict = {}
            if filters["min_area"] is not None:
                area_range["$gte"] = filters["min_area"]
            if filters["max_area"] is not None:
                area_range["$lte"] = filters["max_area"]
            query["area_sqft"] = area_range
        if filters["furnishing"]:
            query["furnishing"] = filters["furnishing"]
        if filters["parking"] is not None:
            query["parking"] = {"$gte": filters["parking"]}
        if filters["floor"] is not None:
            query["floor"] = filters["floor"]
        elif filters["min_floor"] is not None or filters["max_floor"] is not None:
            floor_range: dict = {}
            if filters["min_floor"] is not None:
                floor_range["$gte"] = filters["min_floor"]
            if filters["max_floor"] is not None:
                floor_range["$lte"] = filters["max_floor"]
            query["floor"] = floor_range
        if filters["amenities"]:
            query["amenities.name"] = {"$all": [str(item).strip() for item in filters["amenities"] if str(item).strip()]}
        if filters["construction_status"]:
            query["construction_status"] = filters["construction_status"]
        if filters["exclude_id"] is not None:
            query["_id"] = {"$ne": filters["exclude_id"]}
        if filters["latitude"] is not None:
            query["location"] = {"$near": {"$geometry": {"type": "Point", "coordinates": [filters["longitude"], filters["latitude"]]}, "$maxDistance": filters["radius_km"] * 1000}}
        return query

    @staticmethod
    def _geo_count_query(query: dict) -> dict:
        copied = dict(query)
        near = copied.pop("location")["$near"]
        copied["location"] = {"$geoWithin": {"$centerSphere": [near["$geometry"]["coordinates"], near["$maxDistance"] / 6_378_137]}}
        return copied

    def geospatial_search(self, latitude: float, longitude: float, radius_km: float, **filters: Any) -> Tuple[List[Property], int]:
        """Repository-level geospatial search for a coordinate/radius pair."""
        return self.search(latitude=latitude, longitude=longitude, radius_km=radius_km, **filters)

    # ─── Domain reads ───────────────────────────────────────────────────

    def get_similar(self, property_: Property, limit: int = 6) -> List[Property]:
        price_range = 0.3
        low = property_.price * (1 - price_range)
        high = property_.price * (1 + price_range)
        query = {
            "_id": {"$ne": property_.id},
            "is_active": True,
            "city": property_.city,
            "price": {"$gte": low, "$lte": high},
        }
        same_type = list(
            self.coll.find({**query, "property_type": property_.property_type})
            .limit(limit)
        )
        results = [Property.from_doc(doc) for doc in same_type if doc]
        if len(results) < limit:
            existing = {property_.id, *(p.id for p in results)}
            more = list(
                self.coll.find(
                    {
                        **query,
                        "_id": {"$ne": property_.id, "$nin": list(existing)},
                        "property_type": {"$ne": property_.property_type},
                    }
                ).limit(limit - len(results))
            )
            results.extend(Property.from_doc(doc) for doc in more if doc)
        return results

    def get_featured(self, limit: int = 6) -> List[Property]:
        cursor = (
            self.coll.find({"is_active": True, "is_featured": True})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [Property.from_doc(doc) for doc in cursor if doc]

    # ─── Admin / stats ──────────────────────────────────────────────────

    def count(self, active_only: bool = False, verified_only: bool = False) -> int:
        query: dict = {}
        if active_only:
            query["is_active"] = True
        if verified_only:
            query["verification_status"] = "verified"
        return self.coll.count_documents(query)

    def get_cities(self) -> List[str]:
        return [c for c in self.coll.distinct("city", {"is_active": True}) if c]

    def get_localities(self, city: str) -> List[str]:
        docs = self.coll.find(
            {
                "is_active": True,
                "city": {"$regex": re.escape(city), "$options": "i"},
                "locality": {"$ne": None},
            }
        ).distinct("locality")
        return [loc for loc in docs if loc]

    def count_by_city(self) -> dict:
        pipeline = [
            {"$match": {"is_active": True}},
            {"$group": {"_id": "$city", "count": {"$sum": 1}}},
        ]
        return {
            row["_id"]: row["count"]
            for row in self.coll.aggregate(pipeline)
            if row.get("_id")
        }

    def count_by_type(self) -> dict:
        pipeline = [
            {"$match": {"is_active": True}},
            {"$group": {"_id": "$property_type", "count": {"$sum": 1}}},
        ]
        return {
            row["_id"]: row["count"]
            for row in self.coll.aggregate(pipeline)
            if row.get("_id")
        }

    def verify_property(self, property_id: int, status: str = "verified") -> Optional[Property]:
        updated = self.coll.find_one_and_update(
            {"_id": property_id},
            {"$set": {"verification_status": status}},
            return_document=ReturnDocument.AFTER,
        )
        return Property.from_doc(updated)

    # ─── Writes ─────────────────────────────────────────────────────────

    def create_property(self, property_: Property) -> Property:
        uid = next_id(self.db, self.NAME)
        property_.id = uid
        data = property_.model_dump(exclude={"id"}, exclude_none=True)
        self.coll.insert_one({"_id": uid, **data})
        
        if property_.price:
            self.db["price_history"].insert_one({
                "property_id": uid,
                "old_price": property_.price,
                "new_price": property_.price,
                "changed_at": property_.updated_at,
                "change_type": "initial_listing"
            })
            
        return property_

    insert = create_property  # compatibility for existing seed tooling

    def get_property(self, property_id: int, include_inactive: bool = False) -> Optional[Property]:
        return self.get_by_id(property_id, include_inactive=include_inactive)

    def update_property(self, property_id: int, updates: dict[str, Any]) -> Optional[Property]:
        """Validate a merged document before atomically persisting its update."""
        current = self.coll.find_one({"_id": property_id, "is_active": True})
        if not current:
            return None
            
        old_price = current.get("price")
        
        merged = {**current, **updates, "_id": property_id}
        now = datetime.now(timezone.utc)
        merged["updated_at"] = now
        candidate = Property.from_doc(merged)
        assert candidate is not None
        data = candidate.model_dump(exclude={"id"}, exclude_none=True)
        updated = self.coll.find_one_and_update(
            {"_id": property_id, "is_active": True}, {"$set": data},
            return_document=ReturnDocument.AFTER,
        )
        
        new_price = updated.get("price")
        if old_price and new_price and old_price != new_price:
            change_type = "price_increased" if new_price > old_price else "price_decreased"
            self.db["price_history"].insert_one({
                "property_id": property_id,
                "old_price": old_price,
                "new_price": new_price,
                "changed_at": now,
                "change_type": change_type
            })
            
        return Property.from_doc(updated)

    def delete_property(self, property_id: int) -> bool:
        """Soft-delete a listing to preserve audit/provenance history."""
        result = self.coll.update_one(
            {"_id": property_id, "is_active": True},
            {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count == 1

    def list_properties(self, **filters: Any) -> Tuple[List[Property], int]:
        return self.search(**filters)

    def search_properties(self, **filters: Any) -> Tuple[List[Property], int]:
        return self.search(**filters)

    def count_properties(self, **filters: Any) -> int:
        return self.coll.count_documents(self._build_search_query(**filters))
