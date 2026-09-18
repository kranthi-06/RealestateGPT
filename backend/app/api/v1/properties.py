"""RealEstateGPT - Property API routes"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional, List
from app.core.database import get_db
from app.core.security import get_current_admin, get_optional_user
from app.services.property_service import PropertyService
from app.schemas import (
    PropertyCreate, PropertyResponse, PropertyListResponse, PropertyCardResponse,
    PropertyUpdate, PropertyBulkRequest, PriceIntelligenceResponse,
)
from app.models.user import User

router = APIRouter(prefix="/properties", tags=["Properties"])


@router.post("/bulk", response_model=List[PropertyCardResponse])
async def get_properties_bulk(
    data: PropertyBulkRequest,
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Fetch multiple active property cards by ID (bounded to 12).

    Used by the comparison page so it can load a set in one round trip
    instead of one request per property.
    """
    service = PropertyService(db)
    saved_ids = set()
    if current_user:
        from app.repositories.saved_repo import SavedRepository
        saved_ids = set(SavedRepository(db).get_saved_property_ids(current_user.id))
    items = []
    for prop in service.repo.get_by_ids(data.property_ids):
        resp = PropertyCardResponse.model_validate(prop)
        resp.is_saved = prop.id in saved_ids
        items.append(resp)
    return items


@router.get("", response_model=PropertyListResponse)
async def list_properties(
    q: Optional[str] = Query(None, description="Text search"),
    city: Optional[str] = Query(None),
    locality: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    listing_type: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    bedrooms: Optional[int] = Query(None, ge=0),
    bathrooms: Optional[int] = Query(None, ge=0),
    min_bedrooms: Optional[int] = Query(None, ge=0),
    max_bedrooms: Optional[int] = Query(None, ge=0),
    min_area: Optional[float] = Query(None, ge=0),
    max_area: Optional[float] = Query(None, ge=0),
    furnishing: Optional[str] = Query(None),
    amenities: Optional[List[str]] = Query(None),
    latitude: Optional[float] = Query(None, ge=-90, le=90),
    longitude: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: Optional[float] = Query(None, gt=0, le=100),
    construction_status: Optional[str] = Query(None),
    sort_by: str = Query("created_at", pattern="^(price|area_sqft|created_at|updated_at|bedrooms|bathrooms|price_per_sqft)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Search and list properties with filters."""
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price cannot exceed max_price")
    if min_area is not None and max_area is not None and min_area > max_area:
        raise HTTPException(status_code=422, detail="min_area cannot exceed max_area")
    if any(value is not None for value in (latitude, longitude, radius_km)) and not all(
        value is not None for value in (latitude, longitude, radius_km)
    ):
        raise HTTPException(status_code=422, detail="latitude, longitude and radius_km must be provided together")
    service = PropertyService(db)
    return service.search_properties(
        user_id=current_user.id if current_user else None,
        q=q,
        city=city,
        locality=locality,
        property_type=property_type,
        listing_type=listing_type,
        min_price=min_price,
        max_price=max_price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        min_bedrooms=min_bedrooms,
        max_bedrooms=max_bedrooms,
        min_area=min_area,
        max_area=max_area,
        furnishing=furnishing,
        amenities=amenities,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        construction_status=construction_status,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
async def create_property(
    data: PropertyCreate,
    db=Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Create a property. Restricted to admins regardless of UI state."""
    return PropertyService(db).create_property(data)


@router.get("/featured", response_model=List[PropertyCardResponse])
async def get_featured_properties(
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get featured properties."""
    service = PropertyService(db)
    return service.get_featured(user_id=current_user.id if current_user else None)


@router.get("/cities", response_model=List[str])
async def get_cities(db = Depends(get_db)):
    """Get list of available cities."""
    service = PropertyService(db)
    return service.get_cities()


@router.get("/localities", response_model=List[str])
async def get_localities(city: str = Query(...), db = Depends(get_db)):
    """Get localities for a city."""
    service = PropertyService(db)
    return service.get_localities(city)


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: int,
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get property details by ID."""
    service = PropertyService(db)
    return service.get_property(property_id, user_id=current_user.id if current_user else None)


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: int,
    data: PropertyUpdate,
    db=Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Update a property. Restricted to admins regardless of frontend permissions."""
    return PropertyService(db).update_property(property_id, data)


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_property(
    property_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Soft-delete a property while retaining provenance/audit history."""
    PropertyService(db).delete_property(property_id)


@router.get("/{property_id}/price-intelligence", response_model=PriceIntelligenceResponse)
async def get_property_price_intelligence(
    property_id: int,
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Price intelligence computed ONLY from stored, observed history."""
    from app.services.price_intelligence_service import PriceIntelligenceService

    return PriceIntelligenceService(db).get_price_intelligence(property_id)


@router.get("/{property_id}/similar", response_model=List[PropertyCardResponse])
async def get_similar_properties(
    property_id: int,
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get similar properties."""
    service = PropertyService(db)
    return service.get_similar_properties(property_id, user_id=current_user.id if current_user else None)
