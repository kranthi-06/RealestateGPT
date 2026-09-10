"""RealEstateGPT - Explainable recommendation scoring engine.

Deterministic component scoring with configurable weights. The LLM is never
the source of truth here: every score is derived from database facts
(price, location, amenities, distances, ML estimate).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field as dataclass_field
from typing import Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

FAMILY_AMENITIES = {
    "24/7 Security", "CCTV Surveillance", "Children's Play Area", "Garden",
    "Clubhouse", "Power Backup", "Jogging Track", "Swimming Pool", "Intercom",
}
INVESTOR_AMENITIES = {
    "Gym", "Clubhouse", "Power Backup", "Car Parking", "Swimming Pool",
    "24/7 Security", "Lift",
}
STUDENT_AMENITIES = {"Gym", "Co-working Space", "Library", "Indoor Games", "Power Backup"}
SENIOR_AMENITIES = {"Lift", "Garden", "Power Backup", "24/7 Security", "Yoga Room", "Intercom"}
PET_FRIENDLY_AMENITIES = {"Garden", "Jogging Track", "Children's Play Area"}

LIFESTYLE_NEUTRAL = 0.6  # fraction of max score when lifestyle unspecified

AMENITY_POOLS: Dict[str, set] = {
    "family": FAMILY_AMENITIES,
    "investor": INVESTOR_AMENITIES,
    "student": STUDENT_AMENITIES,
    "senior": SENIOR_AMENITIES,
    "pet_friendly": PET_FRIENDLY_AMENITIES,
}


@dataclass
class ScoreContext:
    """Extra validated data that feeds scoring (never model output)."""
    est_price: Optional[float] = None
    est_low: Optional[float] = None
    est_high: Optional[float] = None
    nearby: Dict[str, float] = dataclass_field(default_factory=dict)  # type -> nearest km
    comparables_median: Optional[float] = None


class PropertyScore:
    def __init__(self) -> None:
        self.components: Dict[str, Dict] = {}
        self.positive: List[str] = []
        self.negative: List[str] = []
        self.details: List[str] = []

    def add(self, key: str, label: str, score: float, max_score: float, detail: Optional[str] = None) -> None:
        self.components[key] = {
            "key": key, "label": label,
            "score": round(min(max(score, 0.0), max_score), 2),
            "max_score": round(max_score, 2),
            "detail": detail,
        }
        if detail:
            self.details.append(detail)

    def total(self) -> float:
        return round(min(100.0, sum(c["score"] for c in self.components.values())), 1)


def _budget_component(price: float, pq, ps: PropertyScore, max_score: float) -> None:
    min_p = pq.get("min_price") if pq else None
    max_p = pq.get("max_price") if pq else None
    if min_p is None and max_p is None:
        ps.add("budget", "Budget", max_score * 0.6, max_score,
               "No budget constraint provided for this match")
        return
    if max_p is not None and min_p is not None and min_p > max_p:
        min_p, max_p = max_p, min_p
    if min_p is not None and max_p is not None and min_p <= price <= max_p:
        ps.add("budget", "Budget", max_score, max_score,
               f"Price within requested range (₹{min_p:,.0f}–₹{max_p:,.0f})")
        ps.positive.append(f"Price ₹{price:,.0f} is within your budget range")
        return
    if max_p is not None and price <= max_p:
        ratio = 1.0 if min_p is None else 0.9
        ps.add("budget", "Budget", max_score * ratio, max_score,
               f"Fits under your ₹{max_p:,.0f} budget")
        ps.positive.append(f"Price ₹{price:,.0f} fits under your ₹{max_p:,.0f} budget")
        return
    if min_p is not None and price >= min_p:
        ps.add("budget", "Budget", max_score, max_score,
               f"Above your ₹{min_p:,.0f} minimum")
        return
    overshoot = (price - max_p) / max_p if max_p else 0.0
    score = max_score * max(0.0, 1.0 - overshoot * 1.5)
    ps.add("budget", "Budget", score, max_score,
           f"₹{price:,.0f} is above your ₹{max_p:,.0f} budget")
    ps.negative.append(f"Price ₹{price:,.0f} exceeds your ₹{max_p:,.0f} budget")
def _location_component(city: str, locality: Optional[str], pq, ps: PropertyScore, max_score: float) -> None:
    req_city = (pq.get("city") or "").strip().lower() if pq else ""
    req_loc = (pq.get("locality") or "").strip().lower() if pq else ""
    prop_loc = (locality or "").strip().lower()
    if not req_city and not req_loc:
        ps.add("location", "Location", max_score * 0.6, max_score, "No location constraint provided")
        return
    if not req_city or req_city in city.lower():
        if req_loc and req_loc in prop_loc:
            ps.add("location", "Location", max_score, max_score,
                   f"Located in {city}, {locality} — matches request")
            ps.positive.append(f"Matches your preferred locality {locality}")
            return
        if req_loc:
            ps.add("location", "Location", max_score * 0.35, max_score,
                   f"{locality or city} differs from requested locality {req_loc}")
            ps.negative.append(f"In {locality} rather than your requested {req_loc}")
            return
        ps.add("location", "Location", max_score * 0.7, max_score,
               f"Located in {city}" + (f", {locality}" if locality else ""))
        ps.positive.append(f"Located in {city}" + (f", {locality}" if locality else ""))
    else:
        ps.add("location", "Location", max_score * 0.2, max_score,
               f"Located in {city}, not the requested {req_city}")
        ps.negative.append(f"In {city} — you asked for {req_city}")


def _property_type_component(prop_type: str, pq, ps: PropertyScore, max_score: float) -> None:
    req = (pq.get("property_type") or "").strip().lower() if pq else ""
    if not req:
        ps.add("property_type", "Property Type", max_score * 0.6, max_score, "No property type constraint")
        return
    if req == prop_type.lower():
        ps.add("property_type", "Property Type", max_score, max_score, f"Matches requested {req}")
        ps.positive.append(f"Correct property type: {prop_type}")
    else:
        ps.add("property_type", "Property Type", max_score * 0.2, max_score,
               f"Is {prop_type}, not the requested {req}")
        ps.negative.append(f"Property type {prop_type} differs from requested {req}")


def _connectivity_component(nearby_reqs, nearby: Dict[str, float], ps: PropertyScore, max_score: float) -> None:
    if not nearby_reqs:
        ps.add("connectivity", "Connectivity", max_score * 0.6, max_score,
               "No nearby-place requirement specified")
def _amenities_component(amenities: List[str], lifestyle: List[str], ps: PropertyScore, max_score: float) -> None:
    pools = [AMENITY_POOLS.get(tag) for tag in lifestyle if AMENITY_POOLS.get(tag)]
    if not pools:
        ps.add("amenities", "Amenities", max_score * 0.7, max_score, "No amenity preference inferred")
        return
    matched: set = set()
    for pool in pools:
        matched |= set(amenities) & pool
    ratio = min(1.0, len(matched) / max(1, min(6, len(pools) * 4)))
    score = max_score * (0.3 + 0.7 * ratio)
    if matched:
        ps.positive.append(f"Has desired amenities: {', '.join(sorted(matched)[:4])}")
    ps.add("amenities", "Amenities", score, max_score,
           f"Matched {len(matched)} preferred amenity/ies: {', '.join(sorted(matched)[:5]) or 'none'}")


def _area_component(area_sqft, pq, ps: PropertyScore, max_score: float) -> None:
    min_a = pq.get("min_area") if pq else None
    max_a = pq.get("max_area") if pq else None
    if area_sqft is None or (min_a is None and max_a is None):
        ps.add("area", "Area", max_score * 0.6, max_score, "No area constraint or area data")
        return
    if min_a is not None and max_a is not None and min_a > max_a:
        min_a, max_a = max_a, min_a
    if (min_a is None or area_sqft >= min_a) and (max_a is None or area_sqft <= max_a):
        ps.add("area", "Area", max_score, max_score, f"{area_sqft:,.0f} sq.ft fits the requested range")
        ps.positive.append(f"Area {area_sqft:,.0f} sq.ft fits your requirement")
    else:
        overshoot = 0.0
        if max_a is not None and area_sqft > max_a:
            overshoot = (area_sqft - max_a) / max_a
        elif min_a is not None and area_sqft < min_a:
            overshoot = (min_a - area_sqft) / min_a
        ps.add("area", "Area", max_score * max(0.2, 1.0 - overshoot * 2), max_score,
               f"Area {area_sqft:,.0f} sq.ft differs from the requested range")
        ps.negative.append(f"Area {area_sqft:,.0f} sq.ft is outside your requested range")


def _lifestyle_component(amenities: List[str], lifestyle: List[str], description: str, pq,
                         ps: PropertyScore, max_score: float) -> None:
    if not lifestyle:
        ps.add("lifestyle", "Lifestyle", max_score * LIFESTYLE_NEUTRAL, max_score,
               "No lifestyle preference explicitly stated")
        return
    desc = (description or "").lower()
    hit_count = 0
    total = 0
    for tag in lifestyle:
        total += 1
        if tag == "family" and ("family" in desc or any(a in amenities for a in FAMILY_AMENITIES)):
            hit_count += 1
        elif tag == "investor" and any(a in amenities for a in INVESTOR_AMENITIES):
            hit_count += 1
        elif tag == "pet_friendly" and ("pet" in desc or bool(PET_FRIENDLY_AMENITIES & set(amenities))):
            hit_count += 1
        elif tag == "senior" and ("senior" in desc or "elderly" in desc or
                                  ("Lift" in amenities and "Garden" in amenities)):
            hit_count += 1
        elif tag == "student" and any(a in amenities for a in STUDENT_AMENITIES):
            hit_count += 1
    ratio = hit_count / total
    ps.add("lifestyle", "Lifestyle", max_score * (0.3 + 0.7 * ratio), max_score,
           f"Fits {hit_count}/{total} lifestyle preference(s): {', '.join(lifestyle)}")
    if ratio >= 0.5:
        ps.positive.append("Suitable for your lifestyle requirements")
        return
    scores = []
    details = []
    for req in nearby_reqs:
        ptype = req.get("type", "").strip().lower()
        max_km = float(req.get("max_distance_km", 2.0))
        dist = nearby.get(ptype)
        if dist is None:
            scores.append(0.3)
            details.append(f"No {ptype} data available nearby")
            continue
        if dist <= max_km:
            scores.append(1.0)
            details.append(f"{ptype.title()} {dist:.1f} km away (within {max_km:g} km)")
            ps.positive.append(f"{ptype.title()} is {dist:.1f} km away — within your {max_km:g} km limit")
        else:
            scores.append(max(0.2, 1.0 - (dist - max_km) / max_km))
def _price_fairness_component(price: float, ctx: ScoreContext, ps: PropertyScore, max_score: float) -> None:
    if ctx.est_price is None:
        ps.add("price_fairness", "Price Fairness", max_score * 0.6, max_score, "No ML price estimate available")
        return
    low = ctx.est_low or ctx.est_price * 0.9
    high = ctx.est_high or ctx.est_price * 1.1
    if low <= price <= high:
        ps.add("price_fairness", "Price Fairness", max_score, max_score,
               f"Listed price near the estimated range ₹{low:,.0f}–₹{high:,.0f}")
        ps.positive.append("Price is consistent with the estimated market range")
    elif price < low:
        ps.add("price_fairness", "Price Fairness", max_score * 0.85, max_score,
               f"Listed price below estimated range (est. ₹{ctx.est_price:,.0f})")
        ps.positive.append("Priced below the estimated market range — potential value")
    else:
        fit = max(0.2, 1.0 - (price - high) / high)
        ps.add("price_fairness", "Price Fairness", max_score * fit, max_score,
               f"Listed price above estimated range (est. ₹{ctx.est_price:,.0f})")
        ps.negative.append("Listed price is above the estimated market range")


def score_property(
    property_data: dict,
    parsed_query: Optional[dict] = None,
    context: Optional[ScoreContext] = None,
    weights: Optional[Dict[str, float]] = None,
) -> dict:
    """Compute explainable match scores from database facts."""
    w = weights or settings.scoring_weights
    ctx = context or ScoreContext()
    ps = PropertyScore()

    price = property_data.get("price") or 0
    _budget_component(price, parsed_query, ps, w.get("budget", 0))
    _location_component(
        property_data.get("city") or "", property_data.get("locality"), parsed_query,
        ps, w.get("location", 0),
    )
    _property_type_component(
        property_data.get("property_type") or "", parsed_query, ps, w.get("property_type", 0),
    )
    _connectivity_component(
        (parsed_query or {}).get("nearby_requirements") or [], ctx.nearby,
        ps, w.get("connectivity", 0),
    )
    _amenities_component(
        property_data.get("amenities") or [], (parsed_query or {}).get("lifestyle") or [],
        ps, w.get("amenities", 0),
    )
    _area_component(property_data.get("area_sqft"), parsed_query, ps, w.get("area", 0))
    _lifestyle_component(
        property_data.get("amenities") or [], (parsed_query or {}).get("lifestyle") or [],
        property_data.get("description") or "", parsed_query, ps, w.get("lifestyle", 0),
    )
    _price_fairness_component(price, ctx, ps, w.get("price_fairness", 0))

    total = ps.total()
    return {
        "overall_score": total,
        "component_scores": [
            ps.components[k] for k in
            ("budget", "location", "property_type", "connectivity",
             "amenities", "area", "lifestyle", "price_fairness")
            if k in ps.components
        ],
        "positive_factors": ps.positive[:5],
        "negative_factors": ps.negative[:5],
        "explanation": _build_explanation(total, property_data, ps),
    }


def _build_explanation(total: float, property_data: dict, ps: PropertyScore) -> str:
    if ps.positive:
        lead = ", ".join(ps.positive[:2])
    elif ps.details:
        lead = ps.details[0]
    else:
        lead = "No strong preference signals provided"
    title = property_data.get("title") or "Property"
    return (
        f"{title} scores {total:.0f}/100 for your criteria. "
        f"Key positive: {lead}."
        + (f" Key concerns: {', '.join(ps.negative[:2])}." if ps.negative else "")
    )