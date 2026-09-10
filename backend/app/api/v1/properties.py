"""RealEstateGPT - Property API routes"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.core.database import get_db
from app.core.security import get_optional_user
from app.services.property_service import PropertyService
from app.schemas import PropertyResponse, PropertyListResponse, PropertyCardResponse
from app.models.user import User

router = APIRouter(prefix="/properties", tags=["Properties"])


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
    min_bedrooms: Optional[int] = Query(None, ge=0),
    max_bedrooms: Optional[int] = Query(None, ge=0),
    min_area: Optional[float] = Query(None, ge=0),
    max_area: Optional[float] = Query(None, ge=0),
    furnishing: Optional[str] = Query(None),
    construction_status: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("created_at"),
    sort_order: Optional[str] = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Search and list properties with filters."""
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
        min_bedrooms=min_bedrooms,
        max_bedrooms=max_bedrooms,
        min_area=min_area,
        max_area=max_area,
        furnishing=furnishing,
        construction_status=construction_status,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.get("/featured", response_model=List[PropertyCardResponse])
async def get_featured_properties(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get featured properties."""
    service = PropertyService(db)
    return service.get_featured(user_id=current_user.id if current_user else None)


@router.get("/cities", response_model=List[str])
async def get_cities(db: Session = Depends(get_db)):
    """Get list of available cities."""
    service = PropertyService(db)
    return service.get_cities()


@router.get("/localities", response_model=List[str])
async def get_localities(city: str = Query(...), db: Session = Depends(get_db)):
    """Get localities for a city."""
    service = PropertyService(db)
    return service.get_localities(city)


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get property details by ID."""
    service = PropertyService(db)
    return service.get_property(property_id, user_id=current_user.id if current_user else None)


@router.get("/{property_id}/similar", response_model=List[PropertyCardResponse])
async def get_similar_properties(
    property_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get similar properties."""
    service = PropertyService(db)
    return service.get_similar_properties(property_id, user_id=current_user.id if current_user else None)
