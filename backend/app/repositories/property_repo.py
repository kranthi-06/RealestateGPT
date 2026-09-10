"""RealEstateGPT - Property repository"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_
from app.models.property import Property, Amenity
from app.models.saved import SavedProperty
from typing import Optional, List, Tuple


class PropertyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, property_id: int) -> Property | None:
        return (
            self.db.query(Property)
            .options(joinedload(Property.amenities))
            .filter(Property.id == property_id, Property.is_active == True)
            .first()
        )

    def get_by_slug(self, slug: str) -> Property | None:
        return (
            self.db.query(Property)
            .options(joinedload(Property.amenities))
            .filter(Property.slug == slug, Property.is_active == True)
            .first()
        )

    def get_by_ids(self, property_ids: List[int]) -> List[Property]:
        return (
            self.db.query(Property)
            .options(joinedload(Property.amenities))
            .filter(Property.id.in_(property_ids), Property.is_active == True)
            .all()
        )

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
        min_bedrooms: Optional[int] = None,
        max_bedrooms: Optional[int] = None,
        min_area: Optional[float] = None,
        max_area: Optional[float] = None,
        furnishing: Optional[str] = None,
        construction_status: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 12,
    ) -> Tuple[List[Property], int]:
        """Search properties with filters, sorting, and pagination."""
        query = self.db.query(Property).options(joinedload(Property.amenities)).filter(Property.is_active == True)

        # Text search across title, description, locality, city, builder
        if q:
            search_term = f"%{q}%"
            query = query.filter(
                or_(
                    Property.title.ilike(search_term),
                    Property.description.ilike(search_term),
                    Property.locality.ilike(search_term),
                    Property.city.ilike(search_term),
                    Property.builder_name.ilike(search_term),
                    Property.project_name.ilike(search_term),
                    Property.address.ilike(search_term),
                )
            )

        # Structured filters
        if city:
            query = query.filter(Property.city.ilike(f"%{city}%"))
        if locality:
            query = query.filter(Property.locality.ilike(f"%{locality}%"))
        if property_type:
            query = query.filter(Property.property_type == property_type)
        if listing_type:
            query = query.filter(Property.listing_type == listing_type)
        if min_price is not None:
            query = query.filter(Property.price >= min_price)
        if max_price is not None:
            query = query.filter(Property.price <= max_price)
        if bedrooms is not None:
            query = query.filter(Property.bedrooms == bedrooms)
        if min_bedrooms is not None:
            query = query.filter(Property.bedrooms >= min_bedrooms)
        if max_bedrooms is not None:
            query = query.filter(Property.bedrooms <= max_bedrooms)
        if min_area is not None:
            query = query.filter(Property.area_sqft >= min_area)
        if max_area is not None:
            query = query.filter(Property.area_sqft <= max_area)
        if furnishing:
            query = query.filter(Property.furnishing == furnishing)
        if construction_status:
            query = query.filter(Property.construction_status == construction_status)

        # Get total count before pagination
        total = query.with_entities(func.count(Property.id)).scalar()

        # Sorting
        sort_column = getattr(Property, sort_by, Property.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Pagination
        offset = (page - 1) * page_size
        properties = query.offset(offset).limit(page_size).all()

        return properties, total

    def get_similar(self, property_: Property, limit: int = 6) -> List[Property]:
        """Find similar properties based on city, type, bedrooms, and price range."""
        price_range = 0.3  # 30% price range
        min_price = property_.price * (1 - price_range)
        max_price = property_.price * (1 + price_range)

        query = (
            self.db.query(Property)
            .options(joinedload(Property.amenities))
            .filter(
                Property.id != property_.id,
                Property.is_active == True,
                Property.city == property_.city,
                Property.price >= min_price,
                Property.price <= max_price,
            )
        )

        # Prefer same property type
        same_type = query.filter(Property.property_type == property_.property_type)
        results = same_type.limit(limit).all()

        if len(results) < limit:
            remaining = limit - len(results)
            existing_ids = [p.id for p in results] + [property_.id]
            more = query.filter(Property.id.notin_(existing_ids)).limit(remaining).all()
            results.extend(more)

        return results

    def get_featured(self, limit: int = 6) -> List[Property]:
        return (
            self.db.query(Property)
            .options(joinedload(Property.amenities))
            .filter(Property.is_active == True, Property.is_featured == True)
            .order_by(Property.created_at.desc())
            .limit(limit)
            .all()
        )

    def count(self, active_only: bool = False, verified_only: bool = False) -> int:
        query = self.db.query(Property)
        if active_only:
            query = query.filter(Property.is_active == True)
        if verified_only:
            query = query.filter(Property.verification_status == "verified")
        return query.count()

    def get_cities(self) -> List[str]:
        result = (
            self.db.query(Property.city)
            .filter(Property.is_active == True)
            .distinct()
            .all()
        )
        return [r[0] for r in result]

    def get_localities(self, city: str) -> List[str]:
        result = (
            self.db.query(Property.locality)
            .filter(Property.is_active == True, Property.city.ilike(f"%{city}%"), Property.locality.isnot(None))
            .distinct()
            .all()
        )
        return [r[0] for r in result]

    def count_by_city(self) -> dict:
        result = (
            self.db.query(Property.city, func.count(Property.id))
            .filter(Property.is_active == True)
            .group_by(Property.city)
            .all()
        )
        return {city: count for city, count in result}

    def count_by_type(self) -> dict:
        result = (
            self.db.query(Property.property_type, func.count(Property.id))
            .filter(Property.is_active == True)
            .group_by(Property.property_type)
            .all()
        )
        return {ptype: count for ptype, count in result}

    def verify_property(self, property_id: int, status: str = "verified") -> Property | None:
        prop = self.db.query(Property).filter(Property.id == property_id).first()
        if prop:
            prop.verification_status = status
            self.db.commit()
            self.db.refresh(prop)
        return prop
