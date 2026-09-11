"""RealEstateGPT - User domain model (MongoDB document)."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(BaseModel):
    id: Optional[int] = None
    email: str
    full_name: str
    hashed_password: str
    phone: Optional[str] = None
    role: str = "user"  # user | admin | agent
    is_active: bool = True
    is_email_verified: bool = False
    preferred_cities: Optional[str] = None  # comma-separated
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @classmethod
    def from_doc(cls, doc: Optional[dict]) -> Optional["User"]:
        if not doc:
            return None
        data = dict(doc)
        data["id"] = data.pop("_id")
        return cls(**data)

    def __repr__(self) -> str:
        return f"<User {self.email}>"