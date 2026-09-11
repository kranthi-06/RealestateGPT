"""RealEstateGPT - Saved items repository (MongoDB).

Enforces ownership in every query: user-scoped reads/writes. Saved property
documents are enriched with the full property card when requested.
"""

from datetime import datetime, timezone
from typing import List, Optional

from pymongo.database import Database

from app.core.database import next_id
from app.models.saved import SavedProperty, SavedSearch, Comparison, SearchHistory


def _utcnow():
    return datetime.now(timezone.utc)


class SavedRepository:
    def __init__(self, db: Database):
        self.db = db
        self.saved_props = db["saved_properties"]
        self.searches = db["saved_searches"]
        self.comparisons = db["comparisons"]
        self.history = db["search_history"]

    # ─── Saved properties ───────────────────────────────────────────────

    def save_property(self, user_id: int, property_id: int, notes: Optional[str] = None) -> SavedProperty:
        existing = self.saved_props.find_one(
            {"user_id": user_id, "property_id": property_id}
        )
        if existing:
            if notes is not None:
                self.saved_props.update_one(
                    {"_id": existing["_id"]}, {"$set": {"notes": notes}}
                )
            return SavedProperty.from_doc(
                self.saved_props.find_one({"_id": existing["_id"]})
            )
        sid = next_id(self.db, "saved_properties")
        doc = {
            "_id": sid, "user_id": user_id, "property_id": property_id,
            "notes": notes, "created_at": _utcnow(),
        }
        self.saved_props.insert_one(doc)
        return SavedProperty.from_doc(doc)

    def unsave_property(self, user_id: int, property_id: int) -> bool:
        result = self.saved_props.delete_one(
            {"user_id": user_id, "property_id": property_id}
        )
        return result.deleted_count > 0

    def get_saved_properties(self, user_id: int) -> List[SavedProperty]:
        """Return saved properties with the joined property card attached."""
        from app.repositories.property_repo import PropertyRepository

        docs = list(
            self.saved_props.find({"user_id": user_id}).sort("created_at", -1)
        )
        items = [SavedProperty.from_doc(doc) for doc in docs if doc]
        engines = PropertyRepository(self.db)
        for item in items:
            item.property = engines.get_by_id(item.property_id)
        return items

    def is_saved(self, user_id: int, property_id: int) -> bool:
        return (
            self.saved_props.find_one({"user_id": user_id, "property_id": property_id})
            is not None
        )

    def get_saved_property_ids(self, user_id: int) -> List[int]:
        docs = self.saved_props.find({"user_id": user_id}, {"property_id": 1})
        return [doc["property_id"] for doc in docs]

    def count_saved(self, user_id: Optional[int] = None) -> int:
        query = {"user_id": user_id} if user_id else {}
        return self.saved_props.count_documents(query)

    # ─── Saved searches ─────────────────────────────────────────────────

    def save_search(self, user_id: int, **kwargs) -> SavedSearch:
        sid = next_id(self.db, "saved_searches")
        doc = {"_id": sid, "user_id": user_id, "created_at": _utcnow(), "updated_at": _utcnow()}
        doc.update({k: v for k, v in kwargs.items() if v is not None})
        self.searches.insert_one(doc)
        return SavedSearch.from_doc(doc)

    def get_saved_searches(self, user_id: int) -> List[SavedSearch]:
        docs = self.searches.find({"user_id": user_id}).sort("created_at", -1)
        return [SavedSearch.from_doc(doc) for doc in docs if doc]

    def delete_saved_search(self, user_id: int, search_id: int) -> bool:
        result = self.searches.delete_one({"_id": search_id, "user_id": user_id})
        return result.deleted_count > 0

    def count_saved_searches(self) -> int:
        return self.searches.count_documents({})

    # ─── Comparisons ────────────────────────────────────────────────────

    def create_comparison(
        self, user_id: int, property_ids: List[int], name: Optional[str] = None
    ) -> Comparison:
        cid = next_id(self.db, "comparisons")
        doc = {
            "_id": cid,
            "user_id": user_id,
            "property_ids": ",".join(str(pid) for pid in property_ids),
            "name": name,
            "created_at": _utcnow(),
        }
        self.comparisons.insert_one(doc)
        return Comparison.from_doc(doc)

    def get_comparison(self, comparison_id: int, user_id: int) -> Optional[Comparison]:
        return Comparison.from_doc(
            self.comparisons.find_one({"_id": comparison_id, "user_id": user_id})
        )

    def get_comparisons(self, user_id: int) -> List[Comparison]:
        docs = self.comparisons.find({"user_id": user_id}).sort("created_at", -1)
        return [Comparison.from_doc(doc) for doc in docs if doc]

    def delete_comparison(self, user_id: int, comparison_id: int) -> bool:
        result = self.comparisons.delete_one({"_id": comparison_id, "user_id": user_id})
        return result.deleted_count > 0

    def count_comparisons(self) -> int:
        return self.comparisons.count_documents({})

    # ─── Search history ─────────────────────────────────────────────────

    def log_search(
        self,
        user_id: Optional[int],
        query_text: Optional[str] = None,
        filters_json: Optional[str] = None,
        result_count: Optional[int] = None,
    ) -> SearchHistory:
        hid = next_id(self.db, "search_history")
        doc = {
            "_id": hid, "user_id": user_id, "query_text": query_text,
            "filters_json": filters_json, "result_count": result_count,
            "created_at": _utcnow(),
        }
        self.history.insert_one(doc)
        return SearchHistory.from_doc(doc)

    def count_searches(self) -> int:
        return self.history.count_documents({})