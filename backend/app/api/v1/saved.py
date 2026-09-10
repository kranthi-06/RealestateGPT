"""RealEstateGPT - Saved items API routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.security import get_current_user
from app.repositories.saved_repo import SavedRepository
from app.repositories.property_repo import PropertyRepository
from app.schemas import (
    SavePropertyRequest, SavedPropertyResponse,
    SaveSearchRequest, SavedSearchResponse,
    ComparisonCreateRequest, ComparisonResponse,
    PropertyResponse, PropertyCardResponse,
)
from app.models.user import User

router = APIRouter(prefix="/saved", tags=["Saved"])


# ─── Saved Properties ────────────────────────────────────

@router.post("/properties", status_code=status.HTTP_201_CREATED)
async def save_property(
    data: SavePropertyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a property to the user's collection."""
    # Verify property exists
    prop_repo = PropertyRepository(db)
    prop = prop_repo.get_by_id(data.property_id)
    if not prop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

    repo = SavedRepository(db)
    saved = repo.save_property(current_user.id, data.property_id, data.notes)
    return {"id": saved.id, "message": "Property saved"}


@router.get("/properties", response_model=List[SavedPropertyResponse])
async def get_saved_properties(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all saved properties."""
    repo = SavedRepository(db)
    saved_items = repo.get_saved_properties(current_user.id)
    results = []
    for item in saved_items:
        results.append(SavedPropertyResponse(
            id=item.id,
            property_id=item.property_id,
            notes=item.notes,
            created_at=item.created_at,
            property=PropertyCardResponse.model_validate(item.property),
        ))
    return results


@router.delete("/properties/{property_id}", status_code=status.HTTP_200_OK)
async def unsave_property(
    property_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a property from saved collection."""
    repo = SavedRepository(db)
    removed = repo.unsave_property(current_user.id, property_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved property not found")
    return {"message": "Property removed from saved"}


# ─── Saved Searches ──────────────────────────────────────

@router.post("/searches", response_model=SavedSearchResponse, status_code=status.HTTP_201_CREATED)
async def save_search(
    data: SaveSearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
):
    """Get all saved searches."""
    repo = SavedRepository(db)
    return [SavedSearchResponse.model_validate(s) for s in repo.get_saved_searches(current_user.id)]


@router.delete("/searches/{search_id}", status_code=status.HTTP_200_OK)
async def delete_saved_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a property comparison set (2-4 properties)."""
    prop_repo = PropertyRepository(db)
    properties = prop_repo.get_by_ids(data.property_ids)
    if len(properties) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 valid properties required for comparison",
        )

    repo = SavedRepository(db)
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
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
):
    """Delete a comparison."""
    repo = SavedRepository(db)
    removed = repo.delete_comparison(current_user.id, comparison_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")
    return {"message": "Comparison deleted"}
