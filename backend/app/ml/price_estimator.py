"""A transparent, catalog-based estimated-price service.

The implementation intentionally remains deterministic until a trained model
artifact is supplied; it reports its method so callers never confuse an
estimate with a guaranteed market value.
"""
from __future__ import annotations

from statistics import median
from typing import Optional, Sequence


class PriceEstimator:
    def estimate(self, prop: dict, catalog: Sequence[dict]) -> dict:
        return self.heuristic_estimate(prop, catalog)

    def heuristic_estimate(self, prop: dict, catalog: Sequence[dict]) -> dict:
        city, kind = prop.get("city"), prop.get("property_type")
        pool = [item for item in catalog if item.get("city") == city and item.get("property_type") == kind]
        if len(pool) < 2:
            pool = [item for item in catalog if item.get("city") == city] or list(catalog)
        per_sqft = [float(item["price_per_sqft"]) for item in pool if item.get("price_per_sqft")]
        area = float(prop.get("area_sqft") or prop.get("carpet_area_sqft") or 400)
        if per_sqft:
            estimated = median(per_sqft) * area
        else:
            prices = [float(item["price"]) for item in pool if item.get("price")]
            estimated = median(prices) if prices else float(prop.get("price") or 0)
        spread = 0.15 if len(pool) >= 5 else 0.2
        return {"estimated_price": round(estimated, 0), "lower_bound": round(estimated * (1 - spread), 0),
                "upper_bound": round(estimated * (1 + spread), 0), "model_version": "comparable-price-v1",
                "mae": None, "rmse": None, "r2": None, "sample_size": len(pool)}


def build_catalog(properties) -> list[dict]:
    return [{"id": prop.id, "city": prop.city, "locality": prop.locality or "unknown",
             "property_type": prop.property_type, "area_sqft": prop.area_sqft,
             "carpet_area_sqft": prop.carpet_area_sqft, "price": prop.price,
             "price_per_sqft": prop.price_per_sqft, "bedrooms": prop.bedrooms,
             "bathrooms": prop.bathrooms, "floor": prop.floor, "property_age": prop.property_age,
             "parking": prop.parking, "amenity_count": len(prop.amenities or [])} for prop in properties]


_estimator: Optional[PriceEstimator] = None


def get_price_estimator() -> PriceEstimator:
    global _estimator
    if _estimator is None:
        _estimator = PriceEstimator()
    return _estimator
