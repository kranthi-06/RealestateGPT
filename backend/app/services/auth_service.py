"""RealEstateGPT - Authentication service"""

from fastapi import HTTPException, status
from app.repositories.user_repo import UserRepository
from app.core.security import verify_password, create_access_token
from app.schemas import UserRegister, UserLogin, TokenResponse, UserResponse


class AuthService:
    def __init__(self, db):
        self.repo = UserRepository(db)

    def register(self, data: UserRegister) -> TokenResponse:
        # Check if user already exists
        existing = self.repo.get_by_email(data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

        user = self.repo.create(
            email=data.email,
            full_name=data.full_name,
            password=data.password,
            phone=data.phone,
        )

        token = create_access_token(data={"sub": str(user.id)})
        return TokenResponse(
            access_token=token,
            user=UserResponse.model_validate(user),
        )

    def login(self, data: UserLogin) -> TokenResponse:
        user = self.repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        token = create_access_token(data={"sub": str(user.id)})
        return TokenResponse(
            access_token=token,
            user=UserResponse.model_validate(user),
        )
