"""Deterministic ranking of web-discovered property candidates.

Ranking signals (weighted, never AI-invented):
  1. query relevance (title keyword overlap with the originating query)
  2. transaction match (rent vs sale)
  3. bedroom match (requested BHK)
  4. price fit (within budget, when a budget is set)
  5. location match (city/locality from the intent)
  6. property type match
  7. freshness (page_fetched / discovered_at age)
  8. source quality (neutral baseline; reserved for trusted-source metadata)
  9. data completeness (populated fields)

The score is a deterministic 0-100 float. AI may *explain* ranking later, but it
never invents ranking evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.discovery.models import PropertyCandidate
from app.schemas.ai import SearchIntent

_SOURCE_QUALITY_BASELINE = 0.6
_FRESH_AGE_SECONDS = 24 * 60 * 60


def _kw_overlap(title: str, query: str) -> float:
    if not title or not query:
        return 0.6
    stop = {"in", "for", "the", "near", "under", "and", "or", "to", "a", "of"}
    title_words = {w for w in title.lower().split() if len(w) > 2}
    query_words = {w for w in query.lower().split() if w not in stop}
    if not title_words or not query_words:
        return 0.6
    return len(title_words & query_words) / len(query_words)


def _age_seconds(candidate: PropertyCandidate) -> Optional[float]:
    reference = candidate.page_fetched or candidate.discovered_at
    if reference is None:
        return None
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - reference).total_seconds())


def _freshness_ratio(candidate: PropertyCandidate) -> float:
    age = _age_seconds(candidate)
    if age is None:
        return 0.5  # unknown freshness: neutral, never claimed
    return max(0.0, min(1.0, 1.0 - (age / (_FRESH_AGE_SECONDS * 7))))


def _completeness(candidate: PropertyCandidate) -> float:
    fields = (
        candidate.price, candidate.bedrooms, candidate.area, candidate.location_text,
        candidate.description, candidate.image_url, candidate.source_name,
    )
    present = sum(1 for field in fields if field is not None)
    return present / len(fields)

def score_candidate(candidate: PropertyCandidate, intent: Optional[SearchIntent] = None, query: str = "") -> dict:
    """Return a competitive score dict with per-signal breakdown (0-100 total)."""
    if intent is None:
        intent = SearchIntent(raw_text=query)
    query = query or intent.raw_text or ""

    signals: list[tuple[str, str, float, str]] = []

    relevance = _kw_overlap(candidate.title or "", query)
    signals.append(("relevance", "Query relevance", relevance, "Keyword overlap between result title and your search"))

    tx_match, tx_detail = 0.6, "Transaction type not specified"
    if intent.listing_type == "rent" and candidate.transaction_type == "rent":
        tx_match, tx_detail = 1.0, "Matches your rental request"
    elif intent.listing_type == "sale" and candidate.transaction_type == "sale":
        tx_match, tx_detail = 1.0, "Matches your purchase request"
    elif candidate.transaction_type:
        tx_match, tx_detail = 0.1, f"Listing is {candidate.transaction_type}, you searched {intent.listing_type}"
    signals.append(("transaction", "Transaction match", tx_match, tx_detail))

    bedroom_match, bedroom_detail = 0.6, "Bedroom count not specified"
    if intent.bedrooms is not None:
        if candidate.bedrooms == intent.bedrooms:
            bedroom_match, bedroom_detail = 1.0, f"Matches your {intent.bedrooms} BHK request"
        elif candidate.bedrooms is None:
            bedroom_match, bedroom_detail = 0.5, "Listing does not state a bedroom count"
        else:
            bedroom_match, bedroom_detail = 0.1, f"Listing is {candidate.bedrooms} BHK, you searched {intent.bedrooms}"
    signals.append(("bedroom", "Bedroom match", bedroom_match, bedroom_detail))

    price_fit, price_detail = 0.6, "No budget was specified"
    if intent.max_price is not None and candidate.price is not None:
        if candidate.price <= intent.max_price:
            price_fit, price_detail = 1.0, f"Listed at {candidate.price}, within your budget"
        else:
            price_fit, price_detail = 0.2, f"Listed at {candidate.price}, above your budget"
    elif intent.max_price is not None and candidate.price is None:
        price_fit, price_detail = 0.5, "Listing does not state a price"
    signals.append(("price", "Price fit", price_fit, price_detail))

    location_match, location_detail = 0.6, "No location was specified"
    if intent.city:
        city_hit = bool(candidate.city and candidate.city.casefold() == intent.city.casefold())
        locality_hit = bool(
            intent.locality and candidate.locality and intent.locality.casefold() in candidate.locality.casefold()
        )
        if locality_hit:
            location_match, location_detail = 1.0, f"Matches requested locality {intent.locality}"
        elif city_hit:
            location_match, location_detail = 0.85, f"Matches requested city {intent.city}"
        elif candidate.city:
            location_match, location_detail = 0.2, f"Listing is in {candidate.city}"
        else:
            location_match, location_detail = 0.5, "Listing location not stated"
    signals.append(("location", "Location match", location_match, location_detail))

    type_match, type_detail = 0.6, "Property type not specified"
    if intent.property_type:
        if candidate.property_type == intent.property_type:
            type_match, type_detail = 1.0, "Matches requested property type"
        elif candidate.property_type is None:
            type_match, type_detail = 0.5, "Listing does not state a property type"
        else:
            type_match, type_detail = 0.15, "Property type differs from your request"
    signals.append(("type", "Property type", type_match, type_detail))

    freshness = _freshness_ratio(candidate)
    signals.append(("freshness", "Freshness", freshness, "Based on discovery/page-fetch time"))

    signals.append(("source", "Source quality", _SOURCE_QUALITY_BASELINE, "Neutral source-quality baseline"))

    completeness = _completeness(candidate)
    signals.append(("completeness", "Data completeness", completeness, "Number of populated listing fields"))

    weights = (0.22, 0.12, 0.12, 0.16, 0.14, 0.07, 0.08, 0.04, 0.05)
    total = sum(ratio * weight for (_, _, ratio, _), weight in zip(signals, weights))
    score = round(min(100.0, total * 100), 1)

    snapshot = [
        {"key": key, "label": label, "ratio": round(ratio, 2), "detail": detail}
        for key, label, ratio, detail in signals
    ]
    return {"score": score, "signals": snapshot, "explanation": (
        f"Deterministic score {score:.0f}/100 from {len(snapshot)} signals "
        "(relevance, transaction, bedrooms, budget, location, type, freshness, completeness)."
    )}
