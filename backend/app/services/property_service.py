"""RealEstateGPT - Property service"""

from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.repositories.property_repo import PropertyRepository
from app.repositories.saved_repo import SavedRepository
from app.schemas import PropertyResponse, PropertyListResponse, PropertyCardResponse
from typing import Optional, List


class PropertyService:
    def __init__(self, db: Session):
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
