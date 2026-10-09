"""RealEstateGPT - Auth API routes"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import settings
from app.core.cookies import clear_auth_cookie, set_auth_cookie
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
async def register(data: UserRegister, request: Request, response: Response, db=Depends(get_db)):
    """Register a new user account and start a session.

    The JWT is returned in the body (for API clients) AND set as an HttpOnly
    cookie so the browser session is not readable from JavaScript.
    """
    auth_limiter.check(_ip(request), settings.RATE_LIMIT_AUTH_REQUESTS, settings.RATE_LIMIT_WINDOW_SECONDS,
                       enabled=settings.RATE_LIMIT_ENABLED)
    token = AuthService(db).register(data)
    set_auth_cookie(response, token.access_token)
    return token


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request, response: Response, db=Depends(get_db)):
    """Login and get an access token (body + HttpOnly session cookie)."""
    auth_limiter.check(_ip(request), settings.RATE_LIMIT_AUTH_REQUESTS, settings.RATE_LIMIT_WINDOW_SECONDS,
                       enabled=settings.RATE_LIMIT_ENABLED)
    token = AuthService(db).login(data)
    set_auth_cookie(response, token.access_token)
    return token


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie. Safe to call when not signed in."""
    clear_auth_cookie(response)
    return {"message": "Signed out"}


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
