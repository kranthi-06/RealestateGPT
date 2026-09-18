"""Price intelligence: computed ONLY from observed, stored history.

current/previous price, percentage change, price-per-sqft / rent-per-sqft,
and observation counts. Charts are only surfaced when enough verified history
exists; otherwise the API reports "not enough verified history" — the LLM
and UI must never invent historical prices.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PriceIntelligenceService:
    """Reads ``price_history`` + the current property record to derive statistics."""

    MIN_HISTORY_FOR_CHART = 2

    def __init__(self, db) -> None:
        self.db = db

    def get_price_intelligence(self, property_id: int, property_doc: Optional[dict] = None) -> Dict[str, Any]:
        doc = property_doc or self.db["properties"].find_one({"_id": property_id})
        if not doc:
            return {"property_id": property_id, "available": False, "message": "Property not found"}

        rows = list(
            self.db["price_history"]
            .find({"property_id": property_id})
            .sort("changed_at", -1)
            .limit(100)
        )
        current = doc.get("price")
        current = float(current) if current else None

        previous: Optional[float] = None
        for row in rows:
            value = float(row["new_price"]) if row.get("new_price") else None
            if value is not None and value != current:
                previous = value
                break

        price_change_pct: Optional[float] = None
        if current and previous:
            price_change_pct = round((current - previous) / previous * 100, 2)

        area = doc.get("area_sqft") or doc.get("area")
        price_per_sqft = doc.get("price_per_sqft")
        if price_per_sqft is None and current and area:
            price_per_sqft = round(current / float(area), 2)

        rent_amount = doc.get("rent_amount") or (current if doc.get("listing_type") == "rent" else None)
        rent_period = doc.get("rent_period")
        rent_per_sqft: Optional[float] = None
        if rent_amount and area:
            rent_per_sqft = round(float(rent_amount) / float(area), 2)

        history: List[Dict[str, Any]] = []
        for row in rows[:10]:
            history.append({
                "changed_at": row.get("changed_at") or row.get("created_at"),
                "old_price": row.get("old_price"),
                "new_price": row.get("new_price"),
                "change_type": row.get("change_type"),
            })

        observations = len(rows)
        change_observations = sum(
            1 for row in rows
            if row.get("new_price") and row.get("old_price")
            and float(row["new_price"]) != float(row["old_price"])
        )

        return {
            "property_id": property_id,
            "available": True,
            "current_price": current,
            "previous_price": previous,
            "price_change_pct": price_change_pct,
            "price_per_sqft": price_per_sqft,
            "rent_amount": rent_amount,
            "rent_period": rent_period,
            "rent_per_sqft": rent_per_sqft,
            "observations": observations,
            "change_observations": change_observations,
            "enough_history": (
                observations >= self.MIN_HISTORY_FOR_CHART
                and change_observations >= 1
            ),
            "history": history,
            "message": None if (observations >= self.MIN_HISTORY_FOR_CHART) else (
                "Not enough verified history."
            ),
            "calculated_at": _utcnow(),
        }