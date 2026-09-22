"""Web property discovery layer.

SearchIntent -> bounded provider queries -> extraction -> deduplication ->
ranking -> persistence in ``web_property_discoveries`` (short-lived) with
``web_search_cache`` for cost control. Never fabricates results.
"""
from app.discovery.service import (
    WebDiscoveryOutcome,
    WebDiscoveryService,
    doc_to_card,
    freshness_label,
)

__all__ = ["WebDiscoveryService", "WebDiscoveryOutcome", "doc_to_card", "freshness_label"]