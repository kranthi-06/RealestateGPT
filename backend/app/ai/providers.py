"""Minimal provider abstraction for grounded response composition."""
from __future__ import annotations

import json


class OfflineProvider:
    name = "offline"

    def complete(self, system: str, user: str) -> str:
        try:
            payload = json.loads(user)
        except (TypeError, ValueError):
            return "I can help search and compare properties using verified platform data."
        results = payload.get("results") or []
        if not results:
            return "I couldn't find an exact match. Try widening the budget or relaxing a requirement."
        lines = [f"I found {len(results)} matching properties:"]
        for index, item in enumerate(results[:3], 1):
            lines.append(f"{index}. {item.get('title', 'Property')} — ₹{item.get('price', 0):,.0f} — {item.get('overall_score', 0):.0f}% match")
        return "\n".join(lines)


def get_provider():
    """External providers can be added behind this stable interface."""
    return OfflineProvider()
