"""PropertyListingDetector: decide whether a search result is actually a
property listing before it becomes a candidate.

Signals (all conservative, never invented):
- BHK / bedroom phrases
- rent / sale price phrases
- area phrases (sqft/sqm)
- locality/city match or mentions
- property terminology (apartment, flat, villa, plot, PG, etc.)
- listing URL patterns (property/listing/pg/detail)
- furnishing / floor / possession phrases

Returns ``{is_property, confidence, reasons}``. Search results that are clearly
news articles, blogs, or generic portals are NOT treated as listings.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.ai.query_parser import CITY_ALIASES
from app.discovery.models import PropertyCandidate
from app.schemas.ai import SearchIntent

logger = logging.getLogger(__name__)

_PROPERTY_TYPE_WORDS = (
    "apartment", "flat", "bhk", "bedroom", "villa", "bungalow", "house",
    "plot", "land", "pg", "hostel", "studio", "penthouse", "office space",
    "shop", "commercial", "builder floor", "penthouse", "duplex",
    "budget", "monthly rent", "for rent", "for sale", "rental",
)

_BEDROOM_RE = re.compile(r"\b\d{1,2}\s*(?:bhk|bedroom|bed|br)\b", re.IGNORECASE)
_RENT_RE = re.compile(r"(?:₹|rs\.?|inr|rupees)?\s*[\d.,]+\s*(?:/month|per month|monthly|/mo|pm\b)", re.IGNORECASE)
_SALE_RE = re.compile(r"(?:₹|rs\.?|inr|rupees)?\s*[\d.,]+\s*(?:lakh|lacs?|crores?|million|cr\b)", re.IGNORECASE)
_AREA_RE = re.compile(r"\b[\d.,]+\s*(?:sq\.?\s?ft|sqft|square\s?feet|sq\.?\s?m|sqm)\b", re.IGNORECASE)
_FURNISHING_RE = re.compile(r"\b(furnished|semi[- ]?furnished|unfurnished)\b", re.IGNORECASE)
_FLOOR_RE = re.compile(r"\b\d+\s*(?:floor|stor|storey)", re.IGNORECASE)
_LISTING_URL_RE = re.compile(r"/(?:property|properties|listing|listings|pg|detail|projects?)(?:/|[-?]|$)", re.IGNORECASE)

# Explicit non-property content signals (news/blog/intro pages).
_NON_PROPERTY_WORDS = (
    "news", "guide", "blog", "article", "how to", "tips", "trending",
    "calculator", "market update", "policy", "faq",
)


@dataclass
class DetectionResult:
    is_property: bool
    confidence: float
    reasons: list[str] = field(default_factory=list)


class PropertyListingDetector:
    def detect(self, candidate: PropertyCandidate, intent: Optional[SearchIntent] = None) -> DetectionResult:
        text = " ".join(
            part for part in (
                candidate.title or "",
                candidate.description or "",
                candidate.location_text or "",
            ) if part
        ).lower()
        url = (candidate.url or "").lower()
        reasons: list[str] = []
        score = 0.0

        lowered = text
        if _BEDROOM_RE.search(lowered):
            score += 0.25
            reasons.append("Contains BHK/bedroom count")
        if candidate.bedrooms is not None:
            score += 0.2
            reasons.append("Bedroom count extracted")
        if _RENT_RE.search(lowered):
            score += 0.2
            reasons.append("Contains monthly rent")
        if _SALE_RE.search(lowered):
            score += 0.2
            reasons.append("Contains sale price")
        if candidate.price is not None:
            score += 0.15
            reasons.append("Price extracted")
        if _AREA_RE.search(lowered):
            score += 0.15
            reasons.append("Contains area")
        if candidate.area is not None:
            score += 0.1
            reasons.append("Area extracted")
        if candidate.city or candidate.locality:
            score += 0.1
            reasons.append("Contains locality/city")
        elif any(re.search(rf"\b{re.escape(city)}\b", lowered) for city in CITY_ALIASES):
            score += 0.1
            reasons.append("Mentions an Indian city")
        if _FURNISHING_RE.search(lowered):
            score += 0.05
        if _FLOOR_RE.search(lowered):
            score += 0.05
        if _LISTING_URL_RE.search(url):
            score += 0.15
            reasons.append("Listing-style URL")
        if re.search(r"for (rent|sale)\b", lowered):
            score += 0.15
            reasons.append("States rent/sale offer")
        hits = sum(1 for word in _PROPERTY_TYPE_WORDS if word in lowered)
        if hits:
            score += min(0.2, hits * 0.04)
            reasons.append("Contains property terminology")

        non_property_hits = sum(1 for word in _NON_PROPERTY_WORDS if word in lowered)
        if non_property_hits:
            score -= min(0.25, non_property_hits * 0.08)

        confidence = round(min(1.0, score), 2)
        is_property = confidence >= 0.30
        if is_property and not reasons:
            reasons.append("Multiple property signals")
        return DetectionResult(is_property=is_property, confidence=confidence, reasons=reasons[:6])