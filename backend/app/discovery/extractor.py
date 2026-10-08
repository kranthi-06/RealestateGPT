"""PropertyCandidateExtractor: WebSearchResult -> PropertyCandidate.

Extracts only fields that can be reasonably supported by the search-result
metadata/snippet/schema. Never hallucinates: missing price -> ``price=None``,
missing BHK -> ``bedrooms=None``, missing image -> ``image_url=None``.

Every populated field is recorded through one of three lightweight extraction
signals; ``extraction_method`` summarizes the dominant signal:
``snippet`` (title/description), ``schema`` (structured provider metadata) or
``metadata`` (provider profile/URL fields). Schema data is treated as
source-provided metadata, never as verification.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.ai.query_parser import CITY_ALIASES, LOCALITIES
from app.providers.web_search.models import WebSearchResult
from app.discovery.models import PropertyCandidate

logger = logging.getLogger(__name__)


class PropertyCandidateExtractor:
    """Deterministic, conservative extraction from a normalized web result."""

    _RENT_RE = re.compile(
        r"([$€£]|usd|eur|gbp|inr|₹|rs\.?|rupees|aed)?\s*([\d][\d,]*(?:\.\d+)?)\s*"
        r"(?:/|\sper\s|\s)?(?:month|mo|pm)\b",
        re.IGNORECASE,
    )
    _NIGHT_RE = re.compile(
        r"([$€£]|usd|eur|gbp|inr|₹|rs\.?|rupees|aed)?\s*([\d][\d,]*(?:\.\d+)?)\s*(?:/|\sper\s)?(?:night|nightly)\b",
        re.IGNORECASE,
    )

    _LARGE_UNIT_RE = re.compile(
        r"([$€£]|usd|eur|gbp|inr|₹|rs\.?|rupees|aed)?\s*([\d][\d,]*(?:\.\d+)?)\s*"
        r"(lakhs?|lacs?|crores?|cr|million|m)\b",
        re.IGNORECASE,
    )

    _BEDROOM_RE = re.compile(
        r"(?<![.\d])(\d{1,2})\s*(?:bhk|bedroom|bed room|bed|br|beds?)(?![a-z])",
        re.IGNORECASE,
    )
    _STUDIO_RE = re.compile(r"\bstudio\b", re.IGNORECASE)

    _AREA_RE = re.compile(
        r"(?<![.\d])([\d][\d,]*(?:\.\d+)?)\s*"
        r"(sq\.?\s?ft|sqft|square\s?feet|sq\.?\s?m|sqm|square\s?meters?)",
        re.IGNORECASE,
    )

    _FURNISHING_RE = re.compile(
        r"\b(semi[- ]?furnished|fully? furnished|unfurnished|furnished)\b",
        re.IGNORECASE,
    )

    _SCHEMA_PRICE_KEYS = ("price", "lowPrice", "highPrice")
    _SCHEMA_BEDROOM_KEYS = ("bedrooms", "numberOfBedrooms", "numberOfRooms")
    _SCHEMA_AREA_KEYS = ("floorSize", "area", "livingArea", "areaSqft")

    _MIN_REALISTIC_PRICE = {
        "INR": 1000,
        "USD": 100,
        "EUR": 100,
        "GBP": 90,
        "AED": 500,
    }

    def extract(self, result: WebSearchResult, intent_city: Optional[str] = None, category: str = "PROPERTY_SALE") -> Optional[PropertyCandidate]:
        """Extract a candidate from one result. Returns None when unusable."""
        text = self._text(result)
        signals: set[str] = set()

        price, currency, transaction, price_method = self._extract_price(result, text)
        bedrooms, bedroom_method = self._extract_bedrooms(result, text)
        area, area_unit, area_method = self._extract_area(result, text)
        location, city, locality = self._extract_location(text, intent_city)
        furnishing = self._extract_furnishing(text)
        image_url = self._safe_image(result.thumbnail_url)

        signals.update(filter(None, (price_method, bedroom_method, area_method)))
        if location:
            signals.add("metadata")

        method = "schema" if signals == {"schema"} else (
            "mixed" if len(signals) > 1 else next(iter(signals), "snippet")
        )

        source_id = self._extract_listing_id(result.url, result.raw_metadata)
        area_sqft = None
        if area is not None:
            area_sqft = round(area * 10.7639, 2) if area_unit == "sqm" else round(area, 2)

        return PropertyCandidate(
            title=result.title[:400] or (result.description or "")[:200] or result.url,
            url=result.url,
            source_domain=result.domain,
            source_name=result.source_name,
            description=result.description,
            price=price,
            currency=currency,
            transaction_type=transaction,
            category=category,
            bedrooms=bedrooms,
            area=area,
            area_unit=area_unit,
            area_sqft=area_sqft,
            location_text=location,
            city=city,
            locality=locality,
            furnishing=furnishing,
            image_url=image_url,
            source_listing_id=source_id,
            page_age=result.page_age,
            page_fetched=result.page_fetched,
            discovered_at=result.retrieved_at,
            confidence=self._confidence(result, price, bedrooms, area, location),
            extraction_method=method,
            provider=result.provider,
        )

    # ── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _text(result: WebSearchResult) -> str:
        parts = [result.title or "", result.description or ""]
        snippets = (result.raw_metadata or {}).get("extra_snippets") or []
        if isinstance(snippets, list):
            parts.extend(str(item) for item in snippets if isinstance(item, str))
        return " ".join(parts)

    def _extract_price(self, result: WebSearchResult, text: str):
        """Return (price, currency, transaction_type, method)."""
        schema_value, schema_currency = self._schema_price(result)
        if schema_value is not None:
            currency = (schema_currency or None) if schema_currency != "" else None
            if currency is None:
                return None, None, None, "schema"
            coerced = self._coerce_price(schema_value)
            if coerced is not None and not self._is_realistic_price(coerced, currency):
                return None, None, None, "schema"
            return coerced, currency, None, "schema"

        def _resolve_currency(symbol: Optional[str]) -> Optional[str]:
            if not symbol:
                return None
            s = symbol.lower()
            if s in ("$", "usd"): return "USD"
            if s in ("€", "eur"): return "EUR"
            if s in ("£", "gbp"): return "GBP"
            if s in ("₹", "rs", "rs.", "inr", "rupees"): return "INR"
            if s == "aed": return "AED"
            return None

        rent_match = self._RENT_RE.search(text)
        if rent_match:
            currency = _resolve_currency(rent_match.group(1))
            if not currency: return None, None, None, "snippet"
            amount = self._coerce_price(rent_match.group(2))
            if amount is None or not self._is_realistic_price(amount, currency, nightly=False):
                return None, None, None, "snippet"
            return amount, currency, "rent", "snippet"

        night_match = self._NIGHT_RE.search(text)
        if night_match:
            currency = _resolve_currency(night_match.group(1))
            if not currency: return None, None, None, "snippet"
            amount = self._coerce_price(night_match.group(2))
            if amount is None or not self._is_realistic_price(amount, currency, nightly=True):
                return None, None, None, "snippet"
            return amount, currency, "rent", "snippet"

        unit_match = self._LARGE_UNIT_RE.search(text)
        if unit_match:
            currency = _resolve_currency(unit_match.group(1))
            if not currency: return None, None, None, "snippet"
            amount = self._coerce_price(unit_match.group(2))
            multiplier = _unit_multiplier((unit_match.group(3) or "").lower())
            if multiplier and amount is not None:
                scaled = amount * multiplier
                if self._is_realistic_price(scaled, currency):
                    return scaled, currency, "sale", "snippet"

        if re.search(r"\b(price|rent|rental|rate|asking)\b", text, re.IGNORECASE):
            generic = re.search(
                r"([$€£]|usd|eur|gbp|inr|₹|rs\.?|rupees|aed)\s{0,2}([\d][\d,]*(?:\.\d+)?)\b(?!\s{0,2}(?:sq\.?|sqft|square|feet|meter|m2|acres?|beds?|br|bhk|baths?|ba|bed|bath|phone|tel|call|fax|id|#|rank|no\.?|number))",
                text,
                re.IGNORECASE,
            )
            if generic:
                currency = _resolve_currency(generic.group(1))
                if not currency: return None, None, None, "snippet"
                amount = self._coerce_price(generic.group(2))
                if amount is None or not self._is_realistic_price(amount, currency):
                    return None, None, None, "snippet"
                return amount, currency, None, "snippet"
        return None, None, None, "snippet"

    def _is_realistic_price(self, price: float, currency: str, *, nightly: bool = False) -> bool:
        if not isinstance(price, (int, float)):
            return False
        price = float(price)
        if price <= 0 or not price == price:
            return False
        if nightly:
            return price >= 5
        minimum = self._MIN_REALISTIC_PRICE.get(currency.upper() if currency else "")
        if minimum is None:
            # Unknown currency: the price is unreliable. Use the INR baseline so
            # that a guessed/USD-only value (e.g. 178 -> "178 INR") is rejected
            # and the UI shows "Price not available" instead of a wrong figure.
            return price >= 1000
        return price >= minimum


    def _schema_price(self, result: WebSearchResult) -> tuple[Optional[float], Optional[str]]:
        for schema in result.schemas or []:
            if not isinstance(schema, dict):
                continue
            for key in self._SCHEMA_PRICE_KEYS:
                node = schema.get("offers") if key.startswith("offers") else schema
                if isinstance(node, dict) and key in node and node[key] is not None:
                    try:
                        return float(node[key]), schema.get("priceCurrency")
                    except (TypeError, ValueError):
                        continue
        return None, None

    @staticmethod
    def _coerce_price(raw: Any) -> Optional[float]:
        try:
            text = str(raw).replace(",", "").strip()
            return round(float(text), 2)
        except (TypeError, ValueError):
            return None

    def _extract_bedrooms(self, result: WebSearchResult, text: str):
        for schema in result.schemas or []:
            if not isinstance(schema, dict):
                continue
            for key in self._SCHEMA_BEDROOM_KEYS:
                raw = schema.get(key)
                if raw is not None:
                    try:
                        value = int(float(raw))
                        if value >= 0:
                            return value, "schema"
                    except (TypeError, ValueError):
                        continue
        match = self._BEDROOM_RE.search(text)
        if match:
            return int(match.group(1)), "snippet"
        if self._STUDIO_RE.search(text):
            return 0, "snippet"
        return None, "snippet"

    def _extract_area(self, result: WebSearchResult, text: str):
        for schema in result.schemas or []:
            if not isinstance(schema, dict):
                continue
            for key in self._SCHEMA_AREA_KEYS:
                raw = schema.get(key)
                if raw is not None:
                    m = re.search(r"([\d][\d,]*(?:\.[\d]+)?)", str(raw))
                    if m is None:
                        continue
                    try:
                        value = float(m.group(1).replace(",", ""))
                    except (TypeError, ValueError):
                        continue
                    unit = "sqft" if "ft" in str(raw).lower() else "sqm"
                    return round(value, 2), unit, "schema"
        match = self._AREA_RE.search(text)
        if match:
            unit_raw = match.group(2).lower()
            unit = "sqft" if ("ft" in unit_raw or "feet" in unit_raw) else "sqm"
            try:
                value = float(match.group(1).replace(",", ""))
                return round(value, 2), unit, "snippet"
            except ValueError:
                return None, None, "snippet"
        return None, None, "snippet"

    def _extract_location(self, text: str, intent_city: Optional[str]):
        """Best-effort city + locality extraction. Never invents coordinates."""
        lowered = text.lower()
        found_city: Optional[str] = None
        found_locality: Optional[str] = None

        if intent_city and intent_city.lower() in CITY_ALIASES:
            found_city = CITY_ALIASES[intent_city.lower()]
        else:
            for alias, city in CITY_ALIASES.items():
                if re.search(rf"\b{re.escape(alias)}\b", lowered):
                    found_city = city
                    break

        if found_city:
            city_key = "Hyderabad" if found_city in ("Bangalore", "Mumbai", "Pune", "Chennai", "Kolkata") else found_city
            city_key = {v: k for k, v in CITY_ALIASES.items()}.get(found_city, found_city)
            localities = LOCALITIES.get(city_key)
            for locality in localities or []:
                if re.search(rf"\b{re.escape(locality.lower())}\b", lowered):
                    found_locality = locality
                    break

        if found_city or found_locality:
            location_text = ", ".join(part for part in (found_locality, found_city) if part) or None
            return location_text, found_city, found_locality
        return None, None, None

    @staticmethod
    def _extract_furnishing(text: str) -> Optional[str]:
        match = PropertyCandidateExtractor._FURNISHING_RE.search(text)
        if not match:
            return None
        raw = match.group(1).lower().replace(" ", "-")
        return raw.replace("fully-", "furnished")

    @staticmethod
    def _safe_image(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        url = url.strip()
        return url if url.startswith(("http://", "https://")) else None

    @staticmethod
    def _extract_listing_id(url: str, raw_metadata: dict) -> Optional[str]:
        patterns = (
            r"/(?:listing|property|properties|pg|detail)(?:s)?[/-]?([0-9a-zA-Z]+)\b",
            r"(?:pid|listing_id|property_id|id)=([0-9a-zA-Z]+)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _confidence(result: WebSearchResult, price, bedrooms, area, location) -> float:
        score = 0.35  # base: title + URL present
        if result.description:
            score += 0.1
        if result.source_name:
            score += 0.1
        if price is not None:
            score += 0.15
        if bedrooms is not None:
            score += 0.1
        if area is not None:
            score += 0.1
        if location:
            score += 0.1
        return round(min(1.0, score), 2)


def _unit_multiplier(unit: str) -> Optional[float]:
    if unit in ("lakhs", "lacs", "lakh", "lac", "l"):
        return 100_000
    if unit in ("crores", "cr", "crore"):
        return 10_000_000
    if unit in ("million", "m"):
        return 1_000_000
    return None
