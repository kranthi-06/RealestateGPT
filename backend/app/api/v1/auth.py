"""RealEstateGPT - Auth API routes"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas import UserRegister, UserLogin, TokenResponse, UserResponse, UserUpdate
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db=Depends(get_db)):
    """Register a new user account."""
    return AuthService(db).register(data)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db=Depends(get_db)):
    """Login and get an access token."""
    return AuthService(db).login(data)


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get the current user's profile."""
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_profile(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Update the current user's profile."""
    repo = UserRepository(db)
    updated = repo.update(
        current_user.id,
        full_name=data.full_name,
        phone=data.phone,
        preferred_cities=data.preferred_cities,
        budget_min=data.budget_min,
        budget_max=data.budget_max,
    )
    return UserResponse.model_validate(updated)