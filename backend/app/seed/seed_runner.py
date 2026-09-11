"""RealEstateGPT - Seed runner: populates MongoDB Atlas with DEMO data.

All seeded records are explicitly marked synthetic (``is_synthetic=True``,
``source_type='demo'``, ``verification_status='unverified'``) and are never
presented as verified market inventory.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import settings
from app.core.database import (
    close_connection, connect, ensure_indexes, get_database, next_id, point,
)
from app.core.security import hash_password
from app.models.property import Property, Amenity
from app.seed.seed_data import AMENITIES, PROPERTIES, _slug


def seed_database():
    """Seed demo data into the configured MongoDB database."""
    if not settings.MONGODB_URI:
        raise RuntimeError("MONGODB_URI is not configured. Cannot seed.")

    connect()
    db = get_database()
    ensure_indexes()

    if db["properties"].count_documents({}) > 0:
        print(f"Database '{settings.MONGODB_DATABASE}' already has properties. Skipping seed.")
        close_connection()
        return

    print("Seeding MongoDB demo data...")

    # 1. Build amenities (embedded per property; ids kept stable for typing)
    amenity_map = {
        a["name"]: Amenity(id=index, name=a["name"], category=a.get("category"), icon=a.get("icon"))
        for index, a in enumerate(AMENITIES, start=1)
    }

    # 2. Insert properties with embedded amenities + GeoJSON location
    for data in PROPERTIES:
        item = dict(data)
        amenity_names = item.pop("amenity_names", [])
        title = item.get("title", "Untitled property")
        if "slug" not in item or not item["slug"]:
            item["slug"] = _slug(title)
        pid = next_id(db, "properties")
        prop = Property.model_validate({
            **item,
            "id": pid,
            "is_synthetic": True,
            "source": "seed_data",
            "source_type": "demo",
            "verification_status": "unverified",
            "data_quality_score": 0.0,
            "amenities": [amenity_map[name].model_dump() for name in amenity_names if name in amenity_map],
        })
        if prop.latitude is not None and prop.longitude is not None:
            prop.location = point(prop.latitude, prop.longitude)
        doc = prop.model_dump(exclude={"id"}, exclude_none=True)
        db["properties"].insert_one({"_id": pid, **doc})
    print(f"  Seeded {len(PROPERTIES)} demo properties")

    # 3. Admin + demo users (demo credentials are for development only)
    admin_id = next_id(db, "users")
    db["users"].insert_one({
        "_id": admin_id,
        "email": "admin@realestate-gpt.com",
        "full_name": "Admin User",
        "hashed_password": hash_password("Admin@123"),
        "role": "admin",
        "is_active": True,
        "is_email_verified": True,
    })
    demo_id = next_id(db, "users")
    db["users"].insert_one({
        "_id": demo_id,
        "email": "demo@realestate-gpt.com",
        "full_name": "Demo User",
        "hashed_password": hash_password("Demo@123"),
        "role": "user",
        "is_active": True,
        "is_email_verified": True,
        "preferred_cities": "Hyderabad,Bangalore",
        "budget_min": 5000000,
        "budget_max": 15000000,
    })
    print("  Seeded admin and demo users")
    print("\nDefault demo accounts (development only):")
    print("  Admin: admin@realestate-gpt.com / Admin@123")
    print("  Demo:  demo@realestate-gpt.com / Demo@123")

    close_connection()
    print("Seed complete.")


if __name__ == "__main__":
    seed_database()