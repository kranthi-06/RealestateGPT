"""RealEstateGPT - Seed runner: populates the database with sample data"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import SessionLocal, engine, Base
from app.models import User, Property, Amenity, property_amenities
from app.core.security import hash_password
from app.seed.seed_data import AMENITIES, PROPERTIES


def seed_database():
    """Seed the database with sample data."""
    # Create tables
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Check if already seeded
        existing_count = db.query(Property).count()
        if existing_count > 0:
            print(f"Database already has {existing_count} properties. Skipping seed.")
            return

        print("Seeding database...")

        # 1. Create amenities
        amenity_map = {}
        for amenity_data in AMENITIES:
            amenity = Amenity(**amenity_data)
            db.add(amenity)
            db.flush()
            amenity_map[amenity.name] = amenity
        print(f"  Created {len(amenity_map)} amenities")

        # 2. Create properties with amenities
        for prop_data in PROPERTIES:
            amenity_names = prop_data.pop("amenity_names", [])
            prop = Property(**prop_data)
            # Add amenities
            for name in amenity_names:
                if name in amenity_map:
                    prop.amenities.append(amenity_map[name])
            db.add(prop)

        db.flush()
        print(f"  Created {len(PROPERTIES)} properties")

        # 3. Create admin user
        admin = User(
            email="admin@realestate-gpt.com",
            full_name="Admin User",
            hashed_password=hash_password("Admin@123"),
            role="admin",
            is_active=True,
            is_email_verified=True,
        )
        db.add(admin)

        # 4. Create demo user
        demo_user = User(
            email="demo@realestate-gpt.com",
            full_name="Demo User",
            hashed_password=hash_password("Demo@123"),
            role="user",
            is_active=True,
            is_email_verified=True,
            preferred_cities="Hyderabad,Bangalore",
            budget_min=5000000,
            budget_max=15000000,
        )
        db.add(demo_user)

        db.commit()
        print("  Created admin and demo users")
        print(f"\nSeed complete! {len(PROPERTIES)} properties, {len(amenity_map)} amenities, 2 users")
        print("\nDefault accounts:")
        print("  Admin: admin@realestate-gpt.com / Admin@123")
        print("  Demo:  demo@realestate-gpt.com / Demo@123")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
