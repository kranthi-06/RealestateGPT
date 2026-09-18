"""RealEstateGPT - Property service"""

from fastapi import HTTPException, status
from app.repositories.property_repo import PropertyRepository
from app.repositories.saved_repo import SavedRepository
from app.models.property import Property
from app.schemas import PropertyCreate, PropertyResponse, PropertyListResponse, PropertyCardResponse, PropertyUpdate
from typing import Optional, List


class PropertyService:
    def __init__(self, db):
        self.repo = PropertyRepository(db)
        self.saved_repo = SavedRepository(db)

    def get_property(self, property_id: int, user_id: Optional[int] = None) -> PropertyResponse:
        prop = self.repo.get_by_id(property_id)
        if not prop:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

        response = PropertyResponse.model_validate(prop)
        if user_id:
            response.is_saved = self.saved_repo.is_saved(user_id, property_id)
        return response

    def create_property(self, data: PropertyCreate) -> PropertyResponse:
        payload = data.model_dump()
        if not payload.get("slug"):
            from app.services.property_ingestion_service import _slug
            payload["slug"] = _slug(f"{payload['source']}-{payload.get('source_id') or payload['title']}")
        property_ = Property.model_validate(payload)
        property_.data_quality_score = self._quality_score(property_)
        if property_.status == 'unknown':
            property_.status = 'active'

        return PropertyResponse.model_validate(self.repo.create_property(property_))

    def update_property(self, property_id: int, data: PropertyUpdate) -> PropertyResponse:
        updates = data.model_dump(exclude_unset=True)
        updated = self.repo.update_property(property_id, updates)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
        updated.data_quality_score = self._quality_score(updated)
        updated = self.repo.update_property(property_id, {"data_quality_score": updated.data_quality_score}) or updated
        return PropertyResponse.model_validate(updated)

    def delete_property(self, property_id: int) -> None:
        if not self.repo.delete_property(property_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

    @staticmethod
    def _quality_score(property_: Property) -> float:
        values = [property_.title, property_.price, property_.property_type, property_.city,
                  property_.source, property_.source_type, property_.source_id,
                  property_.latitude, property_.longitude, property_.area]
        return round(sum(value is not None and value != "" for value in values) / len(values) * 100, 1)

    def get_property_by_slug(self, slug: str, user_id: Optional[int] = None) -> PropertyResponse:
        prop = self.repo.get_by_slug(slug)
        if not prop:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

        response = PropertyResponse.model_validate(prop)
        if user_id:
            response.is_saved = self.saved_repo.is_saved(user_id, prop.id)
        return response

    def search_properties(
        self,
        user_id: Optional[int] = None,
        **kwargs,
    ) -> PropertyListResponse:
        page = kwargs.get("page", 1)
        page_size = kwargs.get("page_size", 12)

        properties, total = self.repo.search(**kwargs)
        total_pages = max(1, (total + page_size - 1) // page_size)

        # Check which properties are saved by this user
        saved_ids = set()
        if user_id:
            saved_ids = set(self.saved_repo.get_saved_property_ids(user_id))

        items = []
        for prop in properties:
            resp = PropertyResponse.model_validate(prop)
            resp.is_saved = prop.id in saved_ids
            items.append(resp)

        return PropertyListResponse(
            properties=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def get_similar_properties(self, property_id: int, user_id: Optional[int] = None) -> List[PropertyCardResponse]:
        prop = self.repo.get_by_id(property_id)
        if not prop:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

        similar = self.repo.get_similar(prop)
        saved_ids = set()
        if user_id:
            saved_ids = set(self.saved_repo.get_saved_property_ids(user_id))

        results = []
        for p in similar:
            resp = PropertyCardResponse.model_validate(p)
            resp.is_saved = p.id in saved_ids
            results.append(resp)
        return results

    def get_featured(self, user_id: Optional[int] = None) -> List[PropertyCardResponse]:
        props = self.repo.get_featured()
        saved_ids = set()
        if user_id:
            saved_ids = set(self.saved_repo.get_saved_property_ids(user_id))

        results = []
        for p in props:
            resp = PropertyCardResponse.model_validate(p)
            resp.is_saved = p.id in saved_ids
            results.append(resp)
        return results

    def get_cities(self) -> List[str]:
        return self.repo.get_cities()

    def get_localities(self, city: str) -> List[str]:
        return self.repo.get_localities(city)
