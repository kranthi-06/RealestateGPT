"""RealEstateGPT - Saved items API routes.

Ownership is enforced in every query (``user_id`` comes from the authenticated
session, never from the request body), so one user can neither read nor modify
another user's saved properties or comparisons.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from typing import List, Optional

from app.core.database import get_db
from app.core.rate_limit import general_limiter
from app.core.security import get_current_user
from app.repositories.saved_repo import SavedRepository
from app.repositories.property_repo import PropertyRepository
from app.schemas import (
    SavePropertyRequest, SavedPropertyResponse, SavedPropertyUpdate,
    SaveSearchRequest, SavedSearchResponse,
    ComparisonCreateRequest, ComparisonResponse,
    PropertyResponse, PropertyCardResponse,
    MAX_SAVED_PROPERTIES_PER_USER, MAX_COMPARISONS_PER_USER,
)
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/saved", tags=["Saved"])

SAVED_PROPERTIES_RATE = (60, 60)      # 60 writes per minute per user
COMPARISON_RATE = (20, 60)            # 20 comparisons per minute per user


def _rate_key(user_id: int, request: Request) -> str:
    """Rate limit per authenticated account, never per spoofable header."""
    return f"saved:{user_id}"


# ─── Saved Properties ────────────────────────────────────

@router.post("/properties", status_code=status.HTTP_201_CREATED)
async def save_property(
    data: SavePropertyRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Save a property to the user's collection (idempotent)."""
    general_limiter.check(_rate_key(current_user.id, request), *SAVED_PROPERTIES_RATE,
                          enabled=True)
    # Verify the property exists and is a live catalogue record before saving.
    prop_repo = PropertyRepository(db)
    prop = prop_repo.get_by_id(data.property_id)
    if not prop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

    repo = SavedRepository(db)
    existing = repo.is_saved(current_user.id, data.property_id)
    if not existing and repo.count_saved_for_user(current_user.id) >= MAX_SAVED_PROPERTIES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You have reached the limit of {MAX_SAVED_PROPERTIES_PER_USER} saved "
                "properties. Remove a listing to save another."
            ),
        )

    saved = repo.save_property(current_user.id, data.property_id, data.notes)
    return {
        "id": saved.id,
        "property_id": data.property_id,
        "already_saved": existing,
        "message": "Property already saved" if existing else "Property saved",
    }


@router.get("/properties", response_model=List[SavedPropertyResponse])
async def get_saved_properties(
    q: Optional[str] = Query(None, max_length=200),
    city: Optional[str] = Query(None, max_length=100),
    locality: Optional[str] = Query(None, max_length=100),
    property_type: Optional[str] = Query(None, max_length=50),
    listing_type: Optional[str] = Query(None, pattern="^(sale|rent)$"),
    bedrooms: Optional[int] = Query(None, ge=0, le=20),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    sort_by: str = Query("created_at", pattern="^(created_at|price|property_id)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Get the signed-in user's saved properties, with search/filter/sort.

    Filtering runs over the joined catalogue records so a saved listing that the
    admin has since removed is skipped instead of crashing the page.
    """
    repo = SavedRepository(db)
    saved_items = repo.get_saved_properties(
        current_user.id, sort_by=sort_by, sort_order=sort_order
    )
    results = []
    for item in saved_items:
        # A saved property whose catalogue record was removed must not crash
        # the whole listing: skip the stale entry and keep serving the rest.
        if item.property is None:
            logger.info(
                "Skipping stale saved record id=%s property_id=%s (property no longer exists)",
                item.id, item.property_id,
            )
            continue
        prop = item.property
        if q and q.strip().lower() not in (prop.title or "").lower():
            continue
        if city and city.strip().lower() not in (prop.city or "").lower():
            continue
        if locality and locality.strip().lower() not in (prop.locality or "").lower():
            continue
        if property_type and prop.property_type != property_type:
            continue
        if listing_type and prop.listing_type != listing_type:
            continue
        if bedrooms is not None and prop.bedrooms != bedrooms:
            continue
        if min_price is not None and prop.price < min_price:
            continue
        if max_price is not None and prop.price > max_price:
            continue
        results.append(SavedPropertyResponse(
            id=item.id,
            property_id=item.property_id,
            notes=item.notes,
            created_at=item.created_at,
            is_saved=True,
            property=PropertyCardResponse.model_validate(prop),
        ))
    return results


@router.get("/properties/ids")
async def get_saved_property_ids(
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Cheap id list used by the UI to keep save buttons in sync everywhere."""
    return {"property_ids": SavedRepository(db).get_saved_property_ids(current_user.id)}


@router.patch("/properties/{property_id}")
async def update_saved_property(
    property_id: int,
    data: SavedPropertyUpdate,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Update the note attached to a saved property."""
    repo = SavedRepository(db)
    if not repo.is_saved(current_user.id, property_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved property not found")
    repo.save_property(current_user.id, property_id, data.notes)
    return {"message": "Saved property updated"}


@router.delete("/properties/{property_id}", status_code=status.HTTP_200_OK)
async def unsave_property(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Remove a property from saved collection."""
    repo = SavedRepository(db)
    removed = repo.unsave_property(current_user.id, property_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved property not found")
    return {"message": "Property removed from saved", "property_id": property_id}


@router.get("/discoveries")
async def get_saved_discoveries(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """List the user's saved web discoveries.

    Deliberately separate from saved catalogue properties: these are web
    results the user bookmarked, never verified inventory.
    """
    from app.discovery.repository import SavedDiscoveryRepository, WebDiscoveryRepository
    from app.discovery.service import doc_to_card

    saved_repo = SavedDiscoveryRepository(db)
    discovery_repo = WebDiscoveryRepository(db)
    cards = []
    for entry in saved_repo.list_for_user(current_user.id, limit=limit):
        doc = discovery_repo.by_id(str(entry.get("discovery_id")))
        if doc is None:
            # The discovery expired and was cleaned up; keep the rest usable.
            logger.info(
                "Skipping stale saved discovery user_id=%s discovery_id=%s (expired)",
                current_user.id, entry.get("discovery_id"),
            )
            continue
        card = doc_to_card(doc, saved=True)
        card["saved_at"] = entry.get("created_at")
        cards.append(card)
    return cards


# ─── Saved Searches ──────────────────────────────────────

@router.post("/searches", response_model=SavedSearchResponse, status_code=status.HTTP_201_CREATED)
async def save_search(
    data: SaveSearchRequest,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Save a search configuration."""
    repo = SavedRepository(db)
    saved = repo.save_search(
        user_id=current_user.id,
        name=data.name,
        city=data.city,
        locality=data.locality,
        property_type=data.property_type,
        min_price=data.min_price,
        max_price=data.max_price,
        bedrooms=data.bedrooms,
        min_area=data.min_area,
        max_area=data.max_area,
        furnishing=data.furnishing,
        query_text=data.query_text,
        notify_enabled=1 if data.notify_enabled else 0,
    )
    return SavedSearchResponse.model_validate(saved)


@router.get("/searches", response_model=List[SavedSearchResponse])
async def get_saved_searches(
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Get all saved searches."""
    repo = SavedRepository(db)
    return [SavedSearchResponse.model_validate(s) for s in repo.get_saved_searches(current_user.id)]


@router.delete("/searches/{search_id}", status_code=status.HTTP_200_OK)
async def delete_saved_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Delete a saved search."""
    repo = SavedRepository(db)
    removed = repo.delete_saved_search(current_user.id, search_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found")
    return {"message": "Search deleted"}


# ─── Comparisons ─────────────────────────────────────────

@router.post("/comparisons", response_model=ComparisonResponse, status_code=status.HTTP_201_CREATED)
async def create_comparison(
    data: ComparisonCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Create a property comparison set (2-4 properties)."""
    general_limiter.check(_rate_key(current_user.id, request), *COMPARISON_RATE, enabled=True)
    prop_repo = PropertyRepository(db)
    properties = prop_repo.get_by_ids(data.property_ids)
    found = {p.id for p in properties}
    missing = [pid for pid in data.property_ids if pid not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"These properties are not available for comparison: {missing}",
        )

    repo = SavedRepository(db)
    if repo.count_comparisons_for_user(current_user.id) >= MAX_COMPARISONS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You have reached the limit of {MAX_COMPARISONS_PER_USER} saved "
                "comparisons. Delete one to save another."
            ),
        )

    comparison = repo.create_comparison(current_user.id, data.property_ids, data.name)

    return ComparisonResponse(
        id=comparison.id,
        name=comparison.name,
        property_ids=comparison.property_ids,
        created_at=comparison.created_at,
        properties=[PropertyResponse.model_validate(p) for p in properties],
    )


@router.get("/comparisons", response_model=List[ComparisonResponse])
async def list_comparisons(
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Get all comparison sets."""
    repo = SavedRepository(db)
    prop_repo = PropertyRepository(db)
    comparisons = repo.get_comparisons(current_user.id)

    results = []
    for comp in comparisons:
        properties = prop_repo.get_by_ids(comp.property_id_list)
        results.append(ComparisonResponse(
            id=comp.id,
            name=comp.name,
            property_ids=comp.property_ids,
            created_at=comp.created_at,
            properties=[PropertyResponse.model_validate(p) for p in properties],
        ))
    return results


@router.get("/comparisons/{comparison_id}", response_model=ComparisonResponse)
async def get_comparison(
    comparison_id: int,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Get a specific comparison with full property details."""
    repo = SavedRepository(db)
    comparison = repo.get_comparison(comparison_id, current_user.id)
    if not comparison:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")

    prop_repo = PropertyRepository(db)
    properties = prop_repo.get_by_ids(comparison.property_id_list)

    return ComparisonResponse(
        id=comparison.id,
        name=comparison.name,
        property_ids=comparison.property_ids,
        created_at=comparison.created_at,
        properties=[PropertyResponse.model_validate(p) for p in properties],
    )


@router.delete("/comparisons/{comparison_id}", status_code=status.HTTP_200_OK)
async def delete_comparison(
    comparison_id: int,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    """Delete a comparison."""
    repo = SavedRepository(db)
    removed = repo.delete_comparison(current_user.id, comparison_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")
    return {"message": "Comparison deleted"}
