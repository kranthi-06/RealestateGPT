"""RealEstateGPT - Saved properties, saved searches, comparisons, search history"""

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class SavedProperty(Base):
    __tablename__ = "saved_properties"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="saved_properties")
    property = relationship("Property", back_populates="saved_by")

    def __repr__(self):
        return f"<SavedProperty user={self.user_id} property={self.property_id}>"


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    city = Column(String(100), nullable=True)
    locality = Column(String(200), nullable=True)
    property_type = Column(String(50), nullable=True)
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    bedrooms = Column(Integer, nullable=True)
    min_area = Column(Float, nullable=True)
    max_area = Column(Float, nullable=True)
    furnishing = Column(String(30), nullable=True)
    query_text = Column(Text, nullable=True)
    notify_enabled = Column(Integer, default=0)  # SQLite-compatible boolean
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="saved_searches")

    def __repr__(self):
        return f"<SavedSearch {self.name}>"


class Comparison(Base):
    __tablename__ = "comparisons"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=True)
    property_ids = Column(String(200), nullable=False)  # comma-separated property IDs
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="comparisons")

    @property
    def property_id_list(self):
        return [int(pid.strip()) for pid in self.property_ids.split(",") if pid.strip()]

    def __repr__(self):
        return f"<Comparison {self.property_ids}>"


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    query_text = Column(Text, nullable=True)
    filters_json = Column(Text, nullable=True)  # JSON string of applied filters
    result_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="search_history")

    def __repr__(self):
        return f"<SearchHistory {self.query_text[:50] if self.query_text else 'filters'}>"
