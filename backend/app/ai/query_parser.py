"""RealEstateGPT - Natural-language property query parser.

Deterministic (rule-based) extraction producing a validated ParsedQuery.
The output is always validated with Pydantic; nothing here trusts the model.
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.schemas.ai import NearbyRequirement, SearchIntent
from app.ai.embeddings import tokenize

# ─── Knowledge tables ──────────────────────────────────────────────────

CITY_ALIASES = {
    "hyderabad": "Hyderabad", "hyd": "Hyderabad", "secunderabad": "Hyderabad",
    "bangalore": "Bangalore", "bengaluru": "Bangalore", "blr": "Bangalore",
    "mumbai": "Mumbai", "bombay": "Mumbai",
    "pune": "Pune",
    "chennai": "Chennai", "madras": "Chennai",
    "kolkata": "Kolkata", "calcutta": "Kolkata",
    "gurgaon": "Gurgaon", "gurugram": "Gurgaon",
    "noida": "Greater Noida", "greater noida": "Greater Noida",
    "delhi": "Delhi", "new delhi": "Delhi",
    "ahmedabad": "Ahmedabad", "jaipur": "Jaipur", "indore": "Indore",
    "lucknow": "Lucknow", "kochi": "Kochi", "cochin": "Kochi",
    "goa": "Goa",
}

LOCALITIES = {
    "Hyderabad": ["HITEC City", "Kondapur", "Madhapur", "Gachibowli", "Begumpet",
                  "Ameerpet", "Banjara Hills", "Jubilee Hills", "Kukatpally",
                  "Manikonda", "Miyapur", "Secunderabad", "LB Nagar", "Appa Junction",
                  "Attapur", "Kompally", "Kollur", "Tellapur", "Rajendra Nagar", "Uppal"],
    "Bangalore": ["Whitefield", "Sarjapura", "Hebbal", "Yelahanka", "Electronic City",
                  "Kanakapura", "Devanahalli", "Koramangala", "Indiranagar", "Bellandur"],
    "Mumbai": ["Thane", "Panvel", "Dombivli", "Mira Road", "Andheri", "Powai", "Navi Mumbai"],
    "Pune": ["Baner", "Hinjawadi", "Kharadi", "Wagholi", "Undri", "Manjri", "Hadapsar"],
    "Chennai": ["Thoraipakkam", "Siruseri", "Medavakkam", "Sholinganallur", "OMR"],
    "Gurgaon": ["Sector 70", "Sector 82", "Sector 43", "Golf Course Road", "Dwarka Expressway"],
    "Greater Noida": ["Noida Extension", "Tech Zone", "Sector 16", "Sector 137"],
    "Kolkata": ["Rajarhat", "New Town", "Ballygunge", "Howrah"],
}

PROPERTY_TYPE_ALIASES = {
    "apartment": "apartment", "flat": "apartment", "flats": "apartment",
    "villa": "villa", "villas": "villa", "bungalow": "villa", "house": "villa",
    "row house": "villa",
    "plot": "plot", "land": "plot", "plots": "plot", "site": "plot",
    "studio": "studio", "penthouse": "penthouse",
}

NEARBY_TYPE_ALIASES = {
    "metro": "metro", "metro station": "metro", "station": "metro",
    "hospital": "hospital", "hospitals": "hospital", "clinic": "hospital",
    "school": "school", "schools": "school",
    "college": "college", "university": "college",
    "supermarket": "supermarket", "grocery": "supermarket", "mall": "mall",
    "shopping mall": "mall", "shopping": "mall",
    "park": "park", "garden": "park",
    "it park": "it_park", "it hub": "it_park", "tech park": "it_park",
    "airport": "airport",
    "transport": "transport", "bus stop": "transport", "bus": "transport",
}

# Match only a known place category, rather than consuming the rest of a sentence.
# The longest aliases take precedence (for example, "metro station" over "metro").
_NEARBY_ALIAS_PATTERN = "|".join(
    re.escape(alias) for alias in sorted(NEARBY_TYPE_ALIASES, key=len, reverse=True)
)

LIFESTYLE_ALIASES = {
    "family": "family", "family-friendly": "family", "kids": "family",
    "investment": "investor", "investor": "investor", "rental": "investor",
    "pet": "pet_friendly", "pets": "pet_friendly", "pet-friendly": "pet_friendly",
    "senior": "senior", "retired": "senior", "elderly": "senior",
    "student": "student", "young professional": "student",
    "first-time": "first_time", "first time": "first_time",
}

FURNISHING_ALIASES = {"furnished": "furnished", "semi-furnished": "semi-furnished", "unfurnished": "unfurnished"}

INTENT_ALIASES = {
    "rent": "rental", "rental": "rental", "lease": "rental", "to-let": "rental", "on rent": "rental",
    "investment": "investment", "invest": "investment", "passive income": "investment", "yield": "investment",
}

_ACCOMMODATION_CATEGORY_ALIASES = {
    "hotel": "HOTEL", "hotels": "HOTEL", "hostel": "HOSTEL", "hostels": "HOSTEL",
    "short stay": "SHORT_STAY", "short-stay": "SHORT_STAY", "weekend stay": "SHORT_STAY",
    "vacation rental": "VACATION_RENTAL", "vacation rentals": "VACATION_RENTAL",
    "holiday home": "VACATION_RENTAL", "holiday homes": "VACATION_RENTAL",
    "airbnb": "VACATION_RENTAL", "vrbo": "VACATION_RENTAL",
    "serviced apartment": "SERVICED_APARTMENT", "serviced apartments": "SERVICED_APARTMENT",
    "service apartment": "SERVICED_APARTMENT", "service apartments": "SERVICED_APARTMENT",
    "pg": "PG", "paying guest": "PG", "co-living": "CO_LIVING", "coliving": "CO_LIVING",
    "accommodation": "ACCOMMODATION", "stay": "ACCOMMODATION", "stays": "ACCOMMODATION",
}

_STOP = {"i", "a", "an", "the", "and", "or", "but", "for", "to", "with", "in", "near", "on", "at", "of",
         "me", "my", "want", "need", "looking", "please", "find", "show", "get", "give", "preferably",
         "within", "under", "over", "around", "about", "close", "is", "be", "are", "that", "this", "from",
         "any", "some", "all", "new", "have", "has", "good", "best", "property", "properties", "flat",
         "apartment", "house", "villa", "plot", "home", "buy", "purchase", "bhk", "sqft", "sq", "ft"}
def _extract_price(text: str) -> dict:
    """Return {min_price, max_price} from phrases like 'under 70 lakh', '50-70 lakhs'."""
    result: dict = {}
    low = text.lower()

    m = re.search(
        rf"(?:under|below|less than|upto|up to|within|max(?:imum)? of?)\s*(?:₹|inr)?\s*{_NUM}\s*(lakhs?|lacs?|crores?|cr|million|m|l)?",
        low)
    if m:
        result["max_price"] = _apply_unit(_to_number(m.group(1)), (m.group(2) or "").lower())

    m = re.search(
        rf"(?:above|over|more than|beyond|min(?:imum)? of?)\s*(?:₹|inr)?\s*{_NUM}\s*(lakhs?|lacs?|crores?|cr|million|m|l)?",
        low)
    if m:
        result["min_price"] = _apply_unit(_to_number(m.group(1)), (m.group(2) or "").lower())

    m = re.search(
        rf"between\s*{_NUM}\s*(lakhs?|lacs?|crores?|cr|million|m|L)?\s*(?:and|to|-)\s*{_NUM}\s*(lakhs?|lacs?|crores?|cr|million|m|L)?",
        low)
    if m:
        lo = _apply_unit(_to_number(m.group(1)), (m.group(2) or "").lower())
        hi = _apply_unit(_to_number(m.group(3)), (m.group(4) or "").lower())
        if lo > hi:
            lo, hi = hi, lo
        result.update({"min_price": lo, "max_price": hi})

    if "min_price" not in result or "max_price" not in result:
        m = re.search(rf"{_NUM}\s*(?:to|-|–)\s*{_NUM}\s*(lakhs?|lacs?|crores?|cr|million|m|L)?", low)
        if m:
            lo = _apply_unit(_to_number(m.group(1)), "")
            hi = _apply_unit(_to_number(m.group(2)), (m.group(3) or "").lower())
            if lo > hi:
                lo, hi = hi, lo
            result.update({"min_price": lo, "max_price": hi})

    if "max_price" not in result:
        m = re.search(rf"{_NUM}\s*(lakhs?|lacs?|crores?|cr|million|m)\b", low)
        if m:
            num = _to_number(m.group(1))
            if num <= 200:
                result["max_price"] = _apply_unit(num, (m.group(2) or "").lower())
    return result


def _extract_nearby(text: str) -> List[dict]:
    """Extract nearby requirements: 'within 2 km of metro', '2 km from hospital', 'near school'."""
    found = []
    for m in re.finditer(
        rf"(\d+(?:\.\d+)?)\s*(?:km|kms|kilometers?)?\s*(?:from|of|to)\s+({_NEARBY_ALIAS_PATTERN})\b",
        text.lower(),
    ):
        dist = float(m.group(1))
        ptype = _resolve_nearby_type(m.group(2).strip())
        if ptype:
            found.append({"type": ptype, "max_distance_km": dist})
    for m in re.finditer(
        rf"(?:near|next to|close to)\s+({_NEARBY_ALIAS_PATTERN})\b", text.lower()
    ):
        ptype = _resolve_nearby_type(m.group(1).strip())
        if ptype and not any(f["type"] == ptype for f in found):
            found.append({"type": ptype, "max_distance_km": 2.0})
    return found


def _resolve_nearby_type(phrase: str) -> Optional[str]:
    lowered = phrase.lower().strip()
    for alias, ptype in NEARBY_TYPE_ALIASES.items():
        if alias in lowered or lowered in alias:
            return ptype
    return None


def _extract_lifestyle(text: str) -> List[str]:
    lowered = text.lower()
    tags = []
    for alias, tag in LIFESTYLE_ALIASES.items():
        if alias in lowered and tag not in tags:
            tags.append(tag)
    return tags


def _extract_intent(text: str) -> str:
    lowered = text.lower()
    for alias, intent in INTENT_ALIASES.items():
        if alias in lowered:
            return intent
    if any(w in lowered for w in ("buy", "purchase", "home", "flat", "apartment", "villa", "plot")):
        return "home_purchase"
    return "unknown"


def _extract_city(text: str) -> Optional[str]:
    lowered = text.lower()
    for alias, city in CITY_ALIASES.items():
        if alias in lowered:
            if len(alias) <= 3 and not re.search(rf"\b{alias}\b", lowered):
                continue
            return city
    return None


def _extract_locality(text: str, city: Optional[str]) -> Optional[str]:
    lowered = text.lower()
    if not city:
        return None
    for locality in LOCALITIES.get(city, []):
        if locality.lower() in lowered:
            return locality
    return None


def _extract_bedrooms(text: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*(?:bhk\b|bedroom|bed room|bed\b)", text.lower())
    if m:
        val = int(float(m.group(1)))
        if 0 <= val <= 20:
            return val
    return None


def _extract_property_type(text: str) -> Optional[str]:
    lowered = text.lower()
    for alias, ptype in PROPERTY_TYPE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return ptype
    return None


def _extract_category(text: str, intent: str) -> str:
    lowered = text.lower()
    for alias, category in _ACCOMMODATION_CATEGORY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return category
    return "PROPERTY_RENT" if intent == "rental" else "PROPERTY_SALE"


def _extract_guests_and_rooms(text: str) -> dict:
    result: dict = {}
    guests = re.search(r"\b(?:for\s+)?(\d{1,2})\s+(?:guests?|people|persons?|adults?)\b", text, re.IGNORECASE)
    rooms = re.search(r"\b(\d{1,2})\s+rooms?\b", text, re.IGNORECASE)
    if guests:
        result["guests"] = int(guests.group(1))
    if rooms:
        result["rooms"] = int(rooms.group(1))
    if re.search(r"\bbreakfast\b", text, re.IGNORECASE):
        result["breakfast_required"] = True
    if re.search(r"\b(?:free\s+)?cancell?ation\b", text, re.IGNORECASE):
        result["cancellation_required"] = True
    # Date parsing deliberately accepts only ISO dates. Ambiguous prose dates
    # require a client date-picker rather than silently assigning a year.
    dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if dates:
        try:
            from datetime import datetime
            result["check_in"] = datetime.fromisoformat(dates[0])
            if len(dates) > 1:
                result["check_out"] = datetime.fromisoformat(dates[1])
        except ValueError:
            pass
    return result


def _extract_furnishing(text: str) -> Optional[str]:
    lowered = text.lower()
    for alias, value in FURNISHING_ALIASES.items():
        if alias in lowered:
            return value
    return None


def _extract_area(text: str) -> dict:
    result: dict = {}
    m = re.search(r"(?:min|above|over|more than)\s*(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|square\s*feet|sqm|sq\.m)", text.lower())
    if m:
        result["min_area"] = _area_to_sqft(float(m.group(1)), m.group(2))
    m = re.search(r"(?:max|under|below|less than)\s*(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|square\s*feet|sqm|sq\.m)", text.lower())
    if m:
        result["max_area"] = _area_to_sqft(float(m.group(1)), m.group(2))
    m = re.search(r"between\s*(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|square\s*feet|sqm|sq\.m)\s*(?:and|to|-)\s*(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|square\s*feet|sqm|sq\.m)", text.lower())
    if m:
        result["min_area"] = _area_to_sqft(float(m.group(1)), m.group(2))
        result["max_area"] = _area_to_sqft(float(m.group(3)), m.group(4))
    return result


def _area_to_sqft(value: float, unit: str) -> float:
    return round(value * 10.7639, 2) if "sqm" in unit or "sq.m" in unit else value


def _extract_commute(text: str) -> dict:
    match = re.search(r"(?:within|under|less than)\s*(\d+)\s*(?:minutes?|mins?)\s+(?:of|from|to)\s+(.+?)(?:[,.]|$)", text.lower())
    if not match:
        return {}
    destination = match.group(2).strip()
    if not destination or len(destination) > 500:
        return {}
    return {"commute_max_minutes": int(match.group(1)), "commute_destination": destination}


def parse_query(text: str) -> SearchIntent:
    """Extract a validated ParsedQuery from a natural-language property request."""
    raw = (text or "").strip()
    lowered = raw.lower()

    price = _extract_price(raw)
    city = _extract_city(lowered)
    locality = _extract_locality(lowered, city)
    nearby = _extract_nearby(lowered)
    lifestyle = _extract_lifestyle(lowered)
    intent = _extract_intent(lowered)
    bedrooms = _extract_bedrooms(lowered)
    ptype = _extract_property_type(lowered)
    category = _extract_category(lowered, intent)
    furnishing = _extract_furnishing(lowered)
    area = _extract_area(lowered)
    commute = _extract_commute(lowered)
    accommodation = _extract_guests_and_rooms(raw)

    listing_type = "rent" if (intent == "rental" or category in {"HOTEL", "HOSTEL", "SHORT_STAY", "VACATION_RENTAL", "SERVICED_APARTMENT", "PG", "CO_LIVING", "ACCOMMODATION"}) else "sale"
    if intent == "unknown" and (bedrooms or city or price.get("max_price") or ptype):
        intent = "home_purchase"

    tokens = [t for t in tokenize(raw) if t not in _STOP and not t.isdigit()]
    keywords: List[str] = []
    for token in tokens:
        if token not in keywords:
            keywords.append(token)

    # Deduplicate nearby requirements (same type, keep the tightest distance).
    nearby_by_type: dict = {}
    for item in nearby:
        nearby_type = item["type"]
        dist = item["max_distance_km"]
        if nearby_type not in nearby_by_type or dist < nearby_by_type[nearby_type]:
            nearby_by_type[nearby_type] = dist
    nearby = [{"type": k, "max_distance_km": v} for k, v in nearby_by_type.items()]

    nearby_requirements = [
        NearbyRequirement(type=item["type"], max_distance_km=item["max_distance_km"])
        for item in nearby
    ]

    return SearchIntent(
        raw_text=raw,
        city=city,
        locality=locality,
        property_type=ptype,
        category=category,
        listing_type=listing_type,
        bedrooms=bedrooms,
        min_price=price.get("min_price"),
        max_price=price.get("max_price"),
        min_area=area.get("min_area"),
        max_area=area.get("max_area"),
        furnishing=furnishing,
        nearby_requirements=nearby_requirements,
        transport_requirement="metro" if any(item.type == "metro" for item in nearby_requirements) else None,
        **commute,
        lifestyle=lifestyle,
        intent=intent,
        keywords=keywords[:24],
        **accommodation,
    )

_NUM = r"(\d+(?:[.,]\d+)?)"


def _to_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _apply_unit(num: float, unit: str) -> float:
    if not unit:
        return num
    if unit in ("l", "lakh", "lakhs", "lac", "lacs"):
        return num * 100000
    if unit in ("cr", "crore", "crores"):
        return num * 10000000
    if unit in ("million", "m"):
        return num * 1000000
    return num
