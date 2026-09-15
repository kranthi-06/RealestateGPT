"""RealEstateGPT - Auth API routes"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import auth_limiter
from app.core.security import get_current_user
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas import UserRegister, UserLogin, TokenResponse, UserResponse, UserUpdate
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _ip(request: Request) -> str:
    """Best-effort client identifier: the direct peer (no header spoofing)."""
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, request: Request, db=Depends(get_db)):
    """Register a new user account."""
    auth_limiter.check(_ip(request), settings.RATE_LIMIT_AUTH_REQUESTS, settings.RATE_LIMIT_WINDOW_SECONDS,
                       enabled=settings.RATE_LIMIT_ENABLED)
    return AuthService(db).register(data)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request, db=Depends(get_db)):
    """Login and get an access token."""
    auth_limiter.check(_ip(request), settings.RATE_LIMIT_AUTH_REQUESTS, settings.RATE_LIMIT_WINDOW_SECONDS,
                       enabled=settings.RATE_LIMIT_ENABLED)
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