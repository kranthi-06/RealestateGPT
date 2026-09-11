"""RealEstateGPT - User repository (MongoDB)."""

from datetime import datetime, timezone
from typing import List, Optional

from pymongo import ReturnDocument
from pymongo.database import Database

from app.core.database import next_id
from app.core.security import hash_password
from app.models.user import User


class UserRepository:
    NAME = "users"

    def __init__(self, db: Database):
        self.db = db
        self.coll = db[self.NAME]

    def get_by_id(self, user_id: int) -> Optional[User]:
        return User.from_doc(self.coll.find_one({"_id": user_id}))

    def get_by_email(self, email: str) -> Optional[User]:
        return User.from_doc(self.coll.find_one({"email": email.lower().strip()}))

    def create(
        self,
        email: str,
        full_name: str,
        password: str,
        phone: Optional[str] = None,
        role: str = "user",
    ) -> User:
        uid = next_id(self.db, self.NAME)
        user = User(
            id=uid,
            email=email.lower().strip(),
            full_name=full_name.strip(),
            hashed_password=hash_password(password),
            phone=phone,
            role=role,
        )
        data = user.model_dump(exclude={"id"}, exclude_none=True)
        self.coll.insert_one({"_id": uid, **data})
        return user

    def update(self, user_id: int, **kwargs) -> Optional[User]:
        updates = {k: v for k, v in kwargs.items() if v is not None}
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc)
            updated = self.coll.find_one_and_update(
                {"_id": user_id},
                {"$set": updates},
                return_document=ReturnDocument.AFTER,
            )
            return User.from_doc(updated)
        return self.get_by_id(user_id)

    def count(self) -> int:
        return self.coll.count_documents({})

    def list_all(self, skip: int = 0, limit: int = 100) -> List[User]:
        docs = self.coll.find().skip(skip).limit(limit)
        return [User.from_doc(doc) for doc in docs if doc]