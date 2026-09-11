"""RealEstateGPT - Admin API routes"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_admin
from app.repositories.property_repo import PropertyRepository
from app.repositories.user_repo import UserRepository
from app.repositories.saved_repo import SavedRepository
from app.schemas import AdminStatsResponse, PropertyResponse, PropertyListResponse
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Get admin dashboard statistics."""
    prop_repo = PropertyRepository(db)
    user_repo = UserRepository(db)
    saved_repo = SavedRepository(db)

    return AdminStatsResponse(
        total_properties=prop_repo.count(),
        active_properties=prop_repo.count(active_only=True),
        verified_properties=prop_repo.count(verified_only=True),
        total_users=user_repo.count(),
        total_saved_properties=saved_repo.count_saved(),
        total_saved_searches=saved_repo.count_saved_searches(),
        total_comparisons=saved_repo.count_comparisons(),
        total_searches=saved_repo.count_searches(),
        properties_by_city=prop_repo.count_by_city(),
        properties_by_type=prop_repo.count_by_type(),
    )


@router.put("/properties/{property_id}/verify")
async def verify_property(
    property_id: int,
    status: str = Query("verified", pattern="^(verified|unverified|rejected)$"),
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Verify or reject a property listing."""
    prop_repo = PropertyRepository(db)
    prop = prop_repo.verify_property(property_id, status)
    if not prop:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Property not found")
    return {"message": f"Property {property_id} status updated to {status}"}
