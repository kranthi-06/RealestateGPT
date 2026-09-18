from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional, List
from app.core.database import get_db
from app.core.security import get_optional_user
from app.services.property_service import PropertyService
from pydantic import BaseModel, Field
from app.schemas import SearchSectionsResponse, SearchSection, PropertyCardResponse, PropertyListResponse

class NearMeRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(5.0, gt=0, le=100)
    q: Optional[str] = None
    property_type: Optional[str] = None
    listing_type: Optional[str] = None
from app.models.user import User

router = APIRouter(prefix="/search", tags=["Search"])

@router.get("/sections", response_model=SearchSectionsResponse)
async def get_search_sections(
    q: Optional[str] = Query(None, description="Text search"),
    city: Optional[str] = Query(None),
    locality: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
    listing_type: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    bedrooms: Optional[int] = Query(None, ge=0),
    latitude: Optional[float] = Query(None, ge=-90, le=90),
    longitude: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: Optional[float] = Query(None, gt=0, le=100),
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Return dynamic sections based on real inventory.
    Only sections with results are returned.
    """
    if any(value is not None for value in (latitude, longitude, radius_km)) and not all(
        value is not None for value in (latitude, longitude, radius_km)
    ):
        raise HTTPException(status_code=422, detail="latitude, longitude and radius_km must be provided together")
        
    service = PropertyService(db)
    user_id = current_user.id if current_user else None
    
    # We will fetch up to 3 sections for demonstration of dynamic inventory grouping
    sections = []
    
    # Define possible categories to group by if not heavily filtered
    if not property_type and not bedrooms:
        categories = [
            {"id": "1bhk", "title": "1 BHK", "filter": {"bedrooms": 1}},
            {"id": "2bhk", "title": "2 BHK", "filter": {"bedrooms": 2}},
            {"id": "3bhk", "title": "3 BHK", "filter": {"bedrooms": 3}},
            {"id": "villas", "title": "Villas", "filter": {"property_type": "villa"}},
            {"id": "houses", "title": "Independent Houses", "filter": {"property_type": "independent_house"}},
        ]
    else:
        # Just return one section "All Results"
        categories = [{"id": "all", "title": "All Results", "filter": {}}]
        
    for cat in categories:
        # merge search filters
        merged = {
            "q": q, "city": city, "locality": locality,
            "property_type": cat["filter"].get("property_type", property_type),
            "listing_type": listing_type,
            "min_price": min_price, "max_price": max_price,
            "bedrooms": cat["filter"].get("bedrooms", bedrooms),
            "latitude": latitude, "longitude": longitude, "radius_km": radius_km,
            "page": 1, "page_size": 4, # only small preview
        }
        resp = service.search_properties(user_id=user_id, **merged)
        if resp.total > 0:
            items = []
            for prop in resp.properties:
                items.append(PropertyCardResponse.model_validate(prop, from_attributes=True))
                
            sections.append(
                SearchSection(
                    id=cat["id"],
                    title=cat["title"],
                    count=resp.total,
                    items=items,
                    next_cursor="2" if resp.total > 4 else None
                )
            )
            
    return SearchSectionsResponse(sections=sections)


@router.post("/near-me", response_model=PropertyListResponse)
async def search_near_me(
    req: NearMeRequest,
    db = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Search properties near the user's location based on intent."""
    service = PropertyService(db)
    user_id = current_user.id if current_user else None
    
    # Delegate to the standard property search with the provided coordinates
    return service.search_properties(
        user_id=user_id,
        q=req.q,
        latitude=req.latitude,
        longitude=req.longitude,
        radius_km=req.radius_km,
        property_type=req.property_type,
        listing_type=req.listing_type,
        page=1,
        page_size=20
    )
