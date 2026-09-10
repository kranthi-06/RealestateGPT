"""RealEstateGPT - Models package"""

from app.models.user import User
from app.models.property import Property, Amenity, property_amenities
from app.models.saved import SavedProperty, SavedSearch, Comparison, SearchHistory
from app.models.platform import (
    AuditLog,
    Conversation,
    Message,
    Recommendation,
    NearbyPlace,
    PricePrediction,
    Document,
    DocumentChunk,
    Notification,
    PropertyVerification,
)

__all__ = [
    "User",
    "Property",
    "Amenity",
    "property_amenities",
    "SavedProperty",
    "SavedSearch",
    "Comparison",
    "SearchHistory",
    "AuditLog",
    "Conversation",
    "Message",
    "Recommendation",
    "NearbyPlace",
    "PricePrediction",
    "Document",
    "DocumentChunk",
    "Notification",
    "PropertyVerification",
]
