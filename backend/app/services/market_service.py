"""Market intelligence service — aggregates REAL stored listings only.

No synthetic listings, no seeded prices, and no external market feeds are used.
Every number returned here is derived from documents that exist in MongoDB, and
each response carries coverage/confidence metadata so the UI can be honest about
what is measured versus estimated.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from app.core.database import get_database

logger = logging.getLogger(__name__)

SQFT_PER_SQ_YARD = 9.0
SQFT_PER_ACRE = 43560.0

# Minimum sample sizes before a statistic is reported as a real measurement.
MIN_SAMPLE = 3
MIN_LOCALITY_SAMPLE = 2


def _mean(values: Iterable[float]) -> Optional[float]:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _median(values: Iterable[float]) -> Optional[float]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    n = len(values)
    mid = n // 2
    if n % 2:
        return float(values[mid])
    return (values[mid - 1] + values[mid]) / 2.0


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    k = (len(ordered) - 1) * pct
    low = math.floor(k)
    high = math.ceil(k)
    if low == high:
        return float(ordered[int(k)])
    return float(ordered[low] * (high - k) + ordered[high] * (k - low))


def _round(value: Optional[float], digits: int = 0) -> Optional[float]:
    if value is None:
        return None
    return round(value, digits)


@dataclass
class MarketFilter:
    city: Optional[str] = None
    locality: Optional[str] = None
    listing_type: Optional[str] = None      # sale | rent | None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None

    def to_mongo(self) -> dict:
        query: dict[str, Any] = {"is_active": True}
        if self.city:
            query["city"] = {"$regex": f"^{_escape(self.city)}", "$options": "i"}
        if self.locality:
            query["locality"] = {"$regex": f"^{_escape(self.locality)}", "$options": "i"}
        if self.listing_type:
            query["listing_type"] = self.listing_type
        if self.property_type:
            query["property_type"] = self.property_type
        if self.bedrooms is not None:
            query["bedrooms"] = self.bedrooms
        if self.min_price is not None or self.max_price is not None:
            price: dict[str, Any] = {}
            if self.min_price is not None:
                price["$gte"] = self.min_price
            if self.max_price is not None:
                price["$lte"] = self.max_price
            query["price"] = price
        return query


def _escape(value: str) -> str:
    """Escape regex metacharacters in user input (prevents ReDoS / injection)."""
    out = []
    for ch in value:
        if ch in r"\^$.|?*+()[]{}":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _area_sqft(doc: dict) -> Optional[float]:
    """Normalise the stored area field to square feet."""
    area = doc.get("area_sqft")
    if isinstance(area, (int, float)) and area > 0:
        return float(area)
    raw = doc.get("area")
    unit = str(doc.get("area_unit") or "sqft").lower()
    if isinstance(raw, (int, float)) and raw > 0:
        if unit == "acre":
            return float(raw) * SQFT_PER_ACRE
        if unit == "sqm":
            return float(raw) * 10.7639
        return float(raw)
    carpet = doc.get("carpet_area_sqft")
    if isinstance(carpet, (int, float)) and carpet > 0:
        return float(carpet)
    return None


def _rent_monthly(doc: dict) -> Optional[float]:
    """Normalise the rent amount to a monthly figure."""
    rent = doc.get("rent_amount")
    if not isinstance(rent, (int, float)) or rent <= 0:
        return None
    period = str(doc.get("rent_period") or "month").lower()
    if period in ("year", "yearly", "annually", "annual", "per_year", "p.a."):
        return float(rent) / 12.0
    if period in ("week", "weekly"):
        return float(rent) * 52.0 / 12.0
    return float(rent)


@dataclass
class PriceStat:
    sample_size: int = 0
    median: Optional[float] = None
    mean: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    is_measured: bool = False

    def to_dict(self) -> dict:
        return {
            "sample_size": self.sample_size,
            "median": _round(self.median),
            "mean": _round(self.mean),
            "p25": _round(self.p25),
            "p75": _round(self.p75),
            "min": _round(self.min),
            "max": _round(self.max),
            "is_measured": self.is_measured,
        }


def _price_stat(values: list[float]) -> PriceStat:
    clean = [v for v in values if isinstance(v, (int, float)) and v > 0]
    if not clean:
        return PriceStat(sample_size=0)
    return PriceStat(
        sample_size=len(clean),
        median=_median(clean),
        mean=_mean(clean),
        p25=_percentile(clean, 0.25),
        p75=_percentile(clean, 0.75),
        min=min(clean),
        max=max(clean),
        is_measured=len(clean) >= MIN_SAMPLE,
    )


@dataclass
class MarketSnapshot:
    query: dict[str, Any]
    localities: list[str] = field(default_factory=list)
    total_listings: int = 0
    sale_listings: int = 0
    rent_listings: int = 0
    apartment_prices: PriceStat = field(default_factory=PriceStat)
    house_prices: PriceStat = field(default_factory=PriceStat)
    land_prices: PriceStat = field(default_factory=PriceStat)
    apartment_psf: PriceStat = field(default_factory=PriceStat)
    house_psf: PriceStat = field(default_factory=PriceStat)
    land_psf: PriceStat = field(default_factory=PriceStat)          # per sq ft
    land_price_per_sq_yard: PriceStat = field(default_factory=PriceStat)
    rents_monthly: PriceStat = field(default_factory=PriceStat)
    rent_psf_monthly: PriceStat = field(default_factory=PriceStat)
    bedroom_breakdown: dict[str, int] = field(default_factory=dict)
    locality_comparison: list[dict] = field(default_factory=list)
    price_history_points: list[dict] = field(default_factory=list)
    price_distribution: list[dict] = field(default_factory=list)
    trend: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "MongoDB verified inventory (RealEstateGPT catalogue)"

    # ── derived indicators ────────────────────────────────────────────────
    @property
    def gross_yield_pct(self) -> Optional[float]:
        if not self.sale_listings or self.rents_monthly.median is None:
            return None
        base = self.apartment_prices.median or self.house_prices.median
        if not base:
            return None
        annual = self.rents_monthly.median * 12
        return round(annual / base * 100, 2)

    @property
    def price_to_rent_ratio(self) -> Optional[float]:
        if self.rents_monthly.median is None:
            return None
        base = self.apartment_prices.median or self.house_prices.median
        if not base:
            return None
        return round(base / (self.rents_monthly.median * 12), 1)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "source": self.source,
            "query": self.query,
            "localities": self.localities,
            "totals": {
                "listings": self.total_listings,
                "sale": self.sale_listings,
                "rent": self.rent_listings,
                "verified_only": True,
            },
            "bedroom_breakdown": self.bedroom_breakdown,
            "apartments": {
                "prices": self.apartment_prices.to_dict(),
                "price_per_sqft": self.apartment_psf.to_dict(),
            },
            "houses": {
                "prices": self.house_prices.to_dict(),
                "price_per_sqft": self.house_psf.to_dict(),
            },
            "land": {
                "prices": self.land_prices.to_dict(),
                "price_per_sqft": self.land_psf.to_dict(),
                "price_per_sq_yard": self.land_price_per_sq_yard.to_dict(),
            },
            "rents": {
                "monthly": self.rents_monthly.to_dict(),
                "price_per_sqft_monthly": self.rent_psf_monthly.to_dict(),
            },
            "locality_comparison": self.locality_comparison,
            "price_history": self.price_history_points,
            "price_distribution": self.price_distribution,
            "trend": self.trend,
            "indicators": {
                "gross_rental_yield_pct": self.gross_yield_pct,
                "price_to_rent_ratio": self.price_to_rent_ratio,
            },
            "coverage": self.coverage,
        }


APARTMENT_TYPES = {"apartment", "flat", "studio", "penthouse", "duplex"}
HOUSE_TYPES = {"house", "villa", "row_house", "bungalow", "farmhouse", "independent_house"}
LAND_TYPES = {"plot", "land", "plotting", "open_land", "agricultural_land"}
COMMERCIAL_TYPES = {"commercial", "office", "shop", "showroom", "warehouse", "godown", " coworking"}
PG_TYPES = {"pg", "co-living", "coliving", "hostel", "paying_guest"}


def _bucket(property_type: str) -> str:
    key = (property_type or "").strip().lower()
    if key in APARTMENT_TYPES:
        return "apartment"
    if key in HOUSE_TYPES:
        return "house"
    if key in LAND_TYPES:
        return "land"
    if key in PG_TYPES:
        return "pg"
    if key in COMMERCIAL_TYPES:
        return "commercial"
    return "other"


def _price_band_label(low: float, high: float) -> str:
    """Human-readable crore/lakh band label for a price histogram bucket."""
    def compact(value: float) -> str:
        if value >= 1_00_00_000:
            return f"{value / 1_00_00_000:.2f} Cr"
        if value >= 1_00_000:
            return f"{value / 1_00_000:.1f} L"
        return f"{value:,.0f}"

    return f"{compact(low)}–{compact(high)}"


class MarketService:
    """Read-only aggregation over the stored property catalogue."""

    def __init__(self, db=None):
        # A pymongo ``Database`` is always truthy-testable against ``None`` only;
        # using ``db or ...`` raises NotImplementedError on a real Database.
        self.db = db if db is not None else get_database()
        self.properties = self.db["properties"]
        self.price_history = self.db["price_history"]

    # ── main entry point ─────────────────────────────────────────────────
    def snapshot(self, flt: MarketFilter, include_history: bool = True) -> MarketSnapshot:
        base = flt.to_mongo()
        snap = MarketSnapshot(query={
            "city": flt.city,
            "locality": flt.locality,
            "listing_type": flt.listing_type,
            "property_type": flt.property_type,
            "bedrooms": flt.bedrooms,
        })

        snap.localities = self._localities(flt)
        counts = self._counts(base)
        snap.total_listings = sum(counts.values())
        snap.sale_listings = counts.get("sale", 0)
        snap.rent_listings = counts.get("rent", 0)

        # Sale-side price statistics, split by property bucket.
        sale_query = dict(base)
        sale_query["listing_type"] = "sale"
        buckets: dict[str, list[float]] = {"apartment": [], "house": [], "land": []}
        psf_by_bucket: dict[str, list[float]] = {"apartment": [], "house": [], "land": []}
        sq_yard_by_bucket: dict[str, list[float]] = {"apartment": [], "house": [], "land": []}
        bedroom_counts: dict[str, int] = {}

        for doc in self.properties.find(sale_query):
            bucket = _bucket(str(doc.get("property_type") or ""))
            price = doc.get("price")
            if bucket not in buckets:
                # Still count bedrooms for the overview.
                beds = doc.get("bedrooms")
                if beds is not None:
                    bedroom_counts[str(int(beds))] = bedroom_counts.get(str(int(beds)), 0) + 1
                continue
            if isinstance(price, (int, float)) and price > 0:
                buckets[bucket].append(float(price))
            area = _area_sqft(doc)
            psf = doc.get("price_per_sqft")
            if not (isinstance(psf, (int, float)) and psf > 0):
                psf = (float(price) / area) if (isinstance(price, (int, float)) and price > 0 and area) else None
            if isinstance(psf, (int, float)) and psf > 0:
                psf_by_bucket[bucket].append(float(psf))
                if bucket == "land":
                    sq_yard_by_bucket[bucket].append(float(psf) * SQFT_PER_SQ_YARD)
            beds = doc.get("bedrooms")
            if beds is not None:
                bedroom_counts[str(int(beds))] = bedroom_counts.get(str(int(beds)), 0) + 1

        snap.apartment_prices = _price_stat(buckets["apartment"])
        snap.house_prices = _price_stat(buckets["house"])
        snap.land_prices = _price_stat(buckets["land"])
        snap.apartment_psf = _price_stat(psf_by_bucket["apartment"])
        snap.house_psf = _price_stat(psf_by_bucket["house"])
        snap.land_psf = _price_stat(psf_by_bucket["land"])
        snap.land_price_per_sq_yard = _price_stat(sq_yard_by_bucket["land"])
        snap.bedroom_breakdown = dict(sorted(bedroom_counts.items(), key=lambda kv: kv[0]))
        snap.price_distribution = self._distribution(buckets["apartment"] or buckets["house"])

        # Rent-side statistics (monthly normalised) from BOTH rent listings and
        # rent-priced sale listings that carry a rent_amount.
        rent_query = dict(base)
        rent_query["$or"] = [{"listing_type": "rent"}, {"rent_amount": {"$gt": 0}}]
        rents: list[float] = []
        rent_psf: list[float] = []
        for doc in self.properties.find(rent_query):
            monthly = _rent_monthly(doc)
            if monthly is None:
                continue
            rents.append(monthly)
            area = _area_sqft(doc)
            if area:
                rent_psf.append(monthly / area)
        snap.rents_monthly = _price_stat(rents)
        snap.rent_psf_monthly = _price_stat(rent_psf)

        # Locality comparison (only when a city-style query is used).
        if not flt.locality:
            snap.locality_comparison = self._locality_comparison(base)

        # Observed price history from the price_history collection.
        if include_history:
            snap.price_history_points = self._price_history(flt)
            snap.trend = self._trend(snap.price_history_points)

        snap.coverage = self._coverage(snap)
        return snap

    # ── helpers ───────────────────────────────────────────────────────────
    def _counts(self, base: dict) -> dict:
        """Listing counts per listing_type.

        Uses an indexed projection scan rather than an aggregation pipeline so
        the counts work on every driver/server combination and never fail the
        whole snapshot when aggregation is unavailable.
        """
        out: dict[str, int] = {}
        for doc in self.properties.find(base, {"listing_type": 1}):
            key = str(doc.get("listing_type"))
            out[key] = out.get(key, 0) + 1
        return out

    def _distribution(self, values: list[float], buckets: int = 6) -> list[dict]:
        """Histogram of observed values, so the UI can draw a real chart.

        Buckets are derived from the actual data range; a single value produces
        a single bucket rather than a fake spread.
        """
        clean = sorted(v for v in values if isinstance(v, (int, float)) and v > 0)
        if not clean:
            return []
        low, high = clean[0], clean[-1]
        if high <= low:
            single = {"label": _price_band_label(low, low), "from": _round(low), "from_value": _round(low),
                      "to": _round(low), "to_value": _round(low), "count": len(clean)}
            return [single]
        width = (high - low) / buckets
        edges = [low + width * i for i in range(buckets)] + [high]
        rows = []
        for i in range(buckets):
            lo, hi = edges[i], edges[i + 1]
            count = sum(1 for v in clean if (lo <= v < hi) or (i == buckets - 1 and v == hi))
            label = _price_band_label(lo, hi)
            rows.append({
                "label": label,
                "from": _round(lo),
                "from_value": _round(lo),
                "to": _round(hi),
                "to_value": _round(hi),
                "count": count,
            })
        return rows

    def _localities(self, flt: MarketFilter) -> list[str]:
        if flt.locality:
            return [flt.locality]
        base = flt.to_mongo()
        try:
            rows = self.properties.distinct("locality", base)
        except Exception as exc:  # pragma: no cover - driver/fallback path
            logger.info("locality_distinct_failed %s", exc)
            # Degrade to a scan-based fallback so the endpoint never 500s.
            seen = {
                doc.get("locality")
                for doc in self.properties.find(base, {"locality": 1})
                if isinstance(doc.get("locality"), str) and doc.get("locality").strip()
            }
            rows = list(seen)
        return sorted({r for r in rows if isinstance(r, str) and r.strip()})

    def _locality_comparison(self, base: dict) -> list[dict]:
        query = dict(base)
        query["listing_type"] = "sale"
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": "$locality",
                "listings": {"$sum": 1},
                "median_price": {"$median": {"input": "$price", "method": "approximate"}},
                "avg_price_per_sqft": {"$avg": "$price_per_sqft"},
            }},
            {"$sort": {"listings": -1, "_id": 1}},
            {"$limit": 20},
        ]
        rows = []
        try:
            for row in self.properties.aggregate(pipeline, allowDiskUse=True):
                name = row.get("_id")
                if not name:
                    continue
                rows.append({
                    "locality": name,
                    "listings": int(row.get("listings") or 0),
                    "median_price": _round(row.get("median_price")),
                    "avg_price_per_sqft": _round(row.get("avg_price_per_sqft")),
                    "measured": int(row.get("listings") or 0) >= MIN_LOCALITY_SAMPLE,
                })
        except Exception as exc:  # pragma: no cover - aggregation fallback
            logger.info("locality_comparison_aggregate_failed %s", exc)
        return rows

    def _price_history(self, flt: MarketFilter) -> list[dict]:
        """Observed price changes for properties inside the market filter."""
        match = flt.to_mongo()
        prop_ids = [doc["_id"] for doc in self.properties.find(match, {"_id": 1})]
        if not prop_ids:
            return []
        pipeline = [
            {"$match": {"property_id": {"$in": prop_ids}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$changed_at"}},
                "observations": {"$sum": 1},
                "avg_new_price": {"$avg": "$new_price"},
                "avg_old_price": {"$avg": "$old_price"},
            }},
            {"$sort": {"_id": 1}},
            {"$limit": 36},
        ]
        rows: list[dict] = []
        try:
            for row in self.price_history.aggregate(pipeline):
                month = row.get("_id")
                if not month:
                    continue
                avg_new = row.get("avg_new_price")
                avg_old = row.get("avg_old_price")
                rows.append({
                    "month": month,
                    "observations": int(row.get("observations") or 0),
                    "avg_price": _round(avg_new) or _round(avg_old),
                    "avg_previous_price": _round(avg_old),
                })
        except Exception as exc:  # pragma: no cover
            logger.info("price_history_aggregate_failed %s", exc)
        return rows

    def _trend(self, points: list[dict]) -> dict:
        if len(points) < 2:
            return {
                "available": False,
                "reason": "Fewer than two months of observed price changes in this area.",
            }
        first = points[0]
        last = points[-1]
        a = first.get("avg_price")
        b = last.get("avg_price")
        if not a or not b:
            return {
                "available": False,
                "reason": "Observed price changes exist but do not include comparable amounts.",
            }
        change_pct = round((b / a - 1) * 100, 2)
        observations = sum(int(p.get("observations") or 0) for p in points)
        return {
            "available": True,
            "from_month": first.get("month"),
            "to_month": last.get("month"),
            "change_pct": change_pct,
            "direction": "up" if change_pct > 0 else ("down" if change_pct < 0 else "flat"),
            "observations": observations,
            "is_measured": observations >= MIN_SAMPLE,
        }

    def _coverage(self, snap: MarketSnapshot) -> dict:
        has_price = snap.sale_listings >= MIN_SAMPLE
        has_psf = snap.apartment_psf.sample_size >= 1 or snap.house_psf.sample_size >= 1
        has_rent = snap.rents_monthly.sample_size >= MIN_SAMPLE
        most_recent = None
        try:
            rows = self.properties.find({"is_active": True}, {"updated_at": 1}).sort("updated_at", -1).limit(1)
            row = next(iter(rows), None)
            if row and row.get("updated_at"):
                most_recent = row["updated_at"].isoformat()
        except Exception as exc:  # pragma: no cover - defensive
            logger.info("coverage_last_updated_failed %s", exc)
        history_months = sorted({p.get("month") for p in snap.price_history_points if p.get("month")})
        return {
            "listings_in_scope": snap.total_listings,
            "price_statistics_measured": has_price,
            "price_per_sqft_measured": has_psf,
            "rent_statistics_measured": has_rent,
            "minimum_sample": MIN_SAMPLE,
            "locality_minimum_sample": MIN_LOCALITY_SAMPLE,
            "last_listing_updated_at": most_recent,
            "observed_price_months": history_months,
            "is_listing_data": True,
            "note": (
                "Statistics are measured from verified stored listings only. "
                "Small samples are reported but flagged as not statistically measured; "
                "no external market feed or generated price is used. Asking prices "
                "are what sellers asked, not completed transaction prices."
            ),
        }

    # ── city roll-up ──────────────────────────────────────────────────────
    def city_totals(self, city: Optional[str] = None) -> list[dict]:
        """Per-city listing totals (optionally filtered to a city prefix)."""
        match: dict = {"is_active": True}
        if city:
            match["city"] = {"$regex": f"^{_escape(city)}", "$options": "i"}
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": "$city",
                "listings": {"$sum": 1},
                "sale": {"$sum": {"$cond": [{"$eq": ["$listing_type", "sale"]}, 1, 0]}},
                "rent": {"$sum": {"$cond": [{"$eq": ["$listing_type", "rent"]}, 1, 0]}},
                "median_price": {"$median": {"input": "$price", "method": "approximate"}},
                "localities": {"$addToSet": "$locality"},
            }},
            {"$project": {
                "listings": 1, "sale": 1, "rent": 1, "median_price": 1,
                "locality_count": {"$size": {"$filter": {
                    "input": "$localities",
                    "as": "l",
                    "cond": {"$and": [{"$ne": ["$$l", None]}, {"$ne": ["$$l", ""]}]},
                }}},
            }},
            {"$sort": {"listings": -1, "_id": 1}},
            {"$limit": 50},
        ]
        rows: list[dict] = []
        try:
            for row in self.properties.aggregate(pipeline, allowDiskUse=True):
                name = row.get("_id")
                if not name:
                    continue
                rows.append({
                    "city": name,
                    "listings": int(row.get("listings") or 0),
                    "sale": int(row.get("sale") or 0),
                    "rent": int(row.get("rent") or 0),
                    "median_price": _round(row.get("median_price")),
                    "locality_count": int(row.get("locality_count") or 0),
                })
        except Exception as exc:  # pragma: no cover
            logger.info("city_totals_aggregate_failed %s", exc)
        return rows
