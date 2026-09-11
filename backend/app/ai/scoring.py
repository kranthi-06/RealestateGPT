"""Deterministic, explainable property-discovery ranking."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings


@dataclass
class ScoreContext:
    nearby: dict[str, float] = field(default_factory=dict)
    est_price: Optional[float] = None
    est_low: Optional[float] = None
    est_high: Optional[float] = None
    comparables_median: Optional[float] = None


def _component(key: str, label: str, ratio: float, maximum: float, detail: str) -> dict:
    return {"key": key, "label": label, "score": round(max(0, min(1, ratio)) * maximum, 2), "max_score": round(maximum, 2), "detail": detail}


def score_property(property_data: dict, parsed_query: Optional[dict] = None, context: Optional[ScoreContext] = None, weights: Optional[dict[str, float]] = None) -> dict:
    """Scores only facts supplied by MongoDB or the configured location provider."""
    query, ctx, weights = parsed_query or {}, context or ScoreContext(), weights or settings.scoring_weights
    components, positive, negative = [], [], []
    price, max_price, min_price = property_data.get("price", 0), query.get("max_price"), query.get("min_price")
    if max_price is None and min_price is None:
        budget_ratio, budget_detail = .6, "No budget constraint provided"
    elif (max_price is None or price <= max_price) and (min_price is None or price >= min_price):
        budget_ratio, budget_detail = 1, "Within requested budget"
        positive.append("Within requested budget")
    else:
        budget_ratio, budget_detail = .1, "Outside requested budget"
        negative.append("Outside requested budget")
    components.append(_component("budget_fit", "Budget fit", budget_ratio, weights.get("budget", 25), budget_detail))

    requested_city, requested_locality = (query.get("city") or "").casefold(), (query.get("locality") or "").casefold()
    city, locality = (property_data.get("city") or "").casefold(), (property_data.get("locality") or "").casefold()
    location_ratio = 1 if requested_locality and requested_locality in locality else (.8 if requested_city and requested_city in city else .6 if not requested_city else .1)
    location_detail = "Matches requested locality" if location_ratio == 1 else ("Matches requested city" if location_ratio >= .8 else "Location does not match request")
    if location_ratio >= .8 and requested_city: positive.append(location_detail)
    components.append(_component("location_fit", "Location fit", location_ratio, weights.get("location", 20), location_detail))

    requested_bedrooms, bedrooms = query.get("bedrooms"), property_data.get("bedrooms")
    bedroom_ratio = .6 if requested_bedrooms is None else (1 if bedrooms == requested_bedrooms else .15)
    if requested_bedrooms is not None and bedroom_ratio == 1: positive.append(f"Matches requested {bedrooms} bedrooms")
    components.append(_component("bedroom_fit", "Bedroom fit", bedroom_ratio, 10, "Matches requested bedrooms" if bedroom_ratio == 1 else "Bedroom count differs or was not requested"))

    requested_type, property_type = (query.get("property_type") or "").casefold(), (property_data.get("property_type") or "").casefold()
    type_ratio = .6 if not requested_type else (1 if requested_type == property_type else .1)
    if requested_type and type_ratio == 1: positive.append("Matches requested property type")
    components.append(_component("property_type_fit", "Property type fit", type_ratio, weights.get("property_type", 15), "Matches requested property type" if type_ratio == 1 else "Property type differs or was not requested"))

    requested_amenities = {item.casefold() for item in query.get("amenities", [])}
    actual_amenities = {item.casefold() for item in property_data.get("amenities", [])}
    amenity_ratio = .7 if not requested_amenities else len(requested_amenities & actual_amenities) / len(requested_amenities)
    if requested_amenities & actual_amenities: positive.append("Matches requested amenities")
    components.append(_component("amenity_fit", "Amenity fit", amenity_ratio, weights.get("amenities", 10), "Amenity match derived from stored listing data"))

    minimum, maximum, area = query.get("min_area"), query.get("max_area"), property_data.get("area_sqft")
    area_ratio = .6 if area is None or (minimum is None and maximum is None) else (1 if (minimum is None or area >= minimum) and (maximum is None or area <= maximum) else .2)
    if area_ratio == 1 and (minimum is not None or maximum is not None): positive.append("Area fits requested range")
    components.append(_component("area_fit", "Area fit", area_ratio, weights.get("area", 5), "Area match derived from stored listing data"))

    requirements = query.get("nearby_requirements") or []
    connectivity_scores = []
    for requirement in requirements:
        category, maximum_km = requirement.get("type"), requirement.get("max_distance_km")
        distance = ctx.nearby.get(category)
        if distance is None: connectivity_scores.append(.4)
        elif distance <= maximum_km:
            connectivity_scores.append(1); positive.append(f"{category.title()} is {distance:.1f} km away")
        else: connectivity_scores.append(.1); negative.append(f"{category.title()} is {distance:.1f} km away, beyond requested distance")
    connectivity_ratio = sum(connectivity_scores) / len(connectivity_scores) if connectivity_scores else .6
    components.append(_component("commute_fit", "Nearby-place fit", connectivity_ratio, weights.get("connectivity", 15), "Based on current OSM nearby-place results" if requirements else "No nearby-place requirement"))

    quality = float(property_data.get("data_quality_score") or 0)
    components.append(_component("data_quality", "Data quality", quality / 100, 10, f"Listing data quality: {quality:.0f}/100"))
    total = round(min(100, sum(item["score"] for item in components)), 1)
    return {"overall_score": total, "component_scores": components, "positive_factors": list(dict.fromkeys(positive))[:5], "negative_factors": list(dict.fromkeys(negative))[:5], "explanation": f"Score {total:.0f}/100, calculated from listing, preference, OSM, and data-quality facts."}
