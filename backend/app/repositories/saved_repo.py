"""RealEstateGPT - Saved items repository"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from app.models.saved import SavedProperty, SavedSearch, Comparison, SearchHistory
from app.models.property import Property
from typing import List, Optional


class SavedRepository:
    def __init__(self, db: Session):
        self.db = db

    # ─── Saved Properties ────────────────────────────────

    def save_property(self, user_id: int, property_id: int, notes: str = None) -> SavedProperty:
        existing = (
            self.db.query(SavedProperty)
            .filter(SavedProperty.user_id == user_id, SavedProperty.property_id == property_id)
            .first()
        )
        if existing:
            if notes is not None:
                existing.notes = notes
                self.db.commit()
                self.db.refresh(existing)
            return existing

        saved = SavedProperty(user_id=user_id, property_id=property_id, notes=notes)
        self.db.add(saved)
        self.db.commit()
        self.db.refresh(saved)
        return saved

    def unsave_property(self, user_id: int, property_id: int) -> bool:
        result = (
            self.db.query(SavedProperty)
            .filter(SavedProperty.user_id == user_id, SavedProperty.property_id == property_id)
            .delete()
        )
        self.db.commit()
        return result > 0

    def get_saved_properties(self, user_id: int) -> List[SavedProperty]:
        return (
            self.db.query(SavedProperty)
            .options(joinedload(SavedProperty.property).joinedload(Property.amenities))
            .filter(SavedProperty.user_id == user_id)
            .order_by(SavedProperty.created_at.desc())
            .all()
        )

    def is_saved(self, user_id: int, property_id: int) -> bool:
        return (
            self.db.query(SavedProperty)
            .filter(SavedProperty.user_id == user_id, SavedProperty.property_id == property_id)
            .first()
        ) is not None

    def get_saved_property_ids(self, user_id: int) -> List[int]:
        result = (
            self.db.query(SavedProperty.property_id)
            .filter(SavedProperty.user_id == user_id)
            .all()
        )
        return [r[0] for r in result]

    def count_saved(self, user_id: Optional[int] = None) -> int:
        query = self.db.query(SavedProperty)
        if user_id:
            query = query.filter(SavedProperty.user_id == user_id)
        return query.count()

    # ─── Saved Searches ──────────────────────────────────

    def save_search(self, user_id: int, **kwargs) -> SavedSearch:
        saved = SavedSearch(user_id=user_id, **kwargs)
        self.db.add(saved)
        self.db.commit()
        self.db.refresh(saved)
        return saved

    def get_saved_searches(self, user_id: int) -> List[SavedSearch]:
        return (
            self.db.query(SavedSearch)
            .filter(SavedSearch.user_id == user_id)
            .order_by(SavedSearch.created_at.desc())
            .all()
        )

    def delete_saved_search(self, user_id: int, search_id: int) -> bool:
        result = (
            self.db.query(SavedSearch)
            .filter(SavedSearch.user_id == user_id, SavedSearch.id == search_id)
            .delete()
        )
        self.db.commit()
        return result > 0

    def count_saved_searches(self) -> int:
        return self.db.query(SavedSearch).count()

    # ─── Comparisons ─────────────────────────────────────

    def create_comparison(self, user_id: int, property_ids: List[int], name: str = None) -> Comparison:
        comparison = Comparison(
            user_id=user_id,
            property_ids=",".join(str(pid) for pid in property_ids),
            name=name,
        )
        self.db.add(comparison)
        self.db.commit()
        self.db.refresh(comparison)
        return comparison

    def get_comparison(self, comparison_id: int, user_id: int) -> Comparison | None:
        return (
            self.db.query(Comparison)
            .filter(Comparison.id == comparison_id, Comparison.user_id == user_id)
            .first()
        )

    def get_comparisons(self, user_id: int) -> List[Comparison]:
        return (
            self.db.query(Comparison)
            .filter(Comparison.user_id == user_id)
            .order_by(Comparison.created_at.desc())
            .all()
        )

    def delete_comparison(self, user_id: int, comparison_id: int) -> bool:
        result = (
            self.db.query(Comparison)
            .filter(Comparison.user_id == user_id, Comparison.id == comparison_id)
            .delete()
        )
        self.db.commit()
        return result > 0

    def count_comparisons(self) -> int:
        return self.db.query(Comparison).count()

    # ─── Search History ──────────────────────────────────

    def log_search(self, user_id: Optional[int], query_text: str = None, filters_json: str = None, result_count: int = None):
        entry = SearchHistory(
            user_id=user_id,
            query_text=query_text,
            filters_json=filters_json,
            result_count=result_count,
        )
        self.db.add(entry)
        self.db.commit()

    def count_searches(self) -> int:
        return self.db.query(SearchHistory).count()
