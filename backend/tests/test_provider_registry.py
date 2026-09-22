"""Property provider registry and adapter unit tests (no database required)."""
import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from app.providers.property import (
    ProviderNotConfiguredError,
    get_property_provider,
    registered_names,
)
from app.providers.property.adapters.admin_import import AdminImportProvider
from app.providers.property.unconfigured import UnconfiguredPropertyProvider


def test_unconfigured_provider_never_returns_data():
    provider = UnconfiguredPropertyProvider()
    assert provider.name == "not_configured"
    with pytest.raises(ProviderNotConfiguredError):
        asyncio.run(provider.fetch_properties(None))
    with pytest.raises(ProviderNotConfiguredError):
        asyncio.run(provider.get_property("x"))
    with pytest.raises(ProviderNotConfiguredError):
        asyncio.run(provider.refresh("x"))
    with pytest.raises(ProviderNotConfiguredError):
        asyncio.run(provider.search({"city": "Hyderabad"}))


def test_registry_registers_admin_import():
    assert "admin_import" in registered_names()


def test_get_provider_defaults_to_sentinel(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.PROPERTY_PROVIDER", "")
    provider = get_property_provider()
    assert provider.name == "not_configured"


def test_admin_import_parses_jsonl_and_paginates():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "listings.jsonl"
        records = [
            {
                "source_listing_id": "A-001", "title": "3BHK at HITEC City",
                "price": 7500000, "property_type": "apartment", "city": "Hyderabad",
                "locality": "HITEC City", "bedrooms": 3,
                "images": ["https://example.com/a.jpg"],
            },
            {
                "source_listing_id": "A-002", "title": "2BHK Kondapur",
                "price": 5500000, "property_type": "apartment", "city": "Hyderabad",
                "locality": "Kondapur", "bedrooms": 2, "status": "sold",
            },
        ]
        path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

        provider = AdminImportProvider(file_path=str(path))

        async def fetch_all():
            out, cursor = await provider.fetch_properties(None)
            eager = list(out)
            while cursor:
                more, cursor = await provider.fetch_properties(cursor)
                eager.extend(more)
            return eager

        fetched = asyncio.run(fetch_all())
        assert len(fetched) == 2
        assert fetched[0]["source_listing_id"] == "A-001"


def test_admin_import_refresh_marks_absent_listing_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "listings.jsonl"
        path.write_text(json.dumps({
            "source_listing_id": "K-1", "title": "Villa", "price": 10000000,
            "property_type": "villa", "city": "Pune",
        }), encoding="utf-8")
        provider = AdminImportProvider(file_path=str(path))

        from app.providers.property.errors import ProviderListingNotFoundError
        with pytest.raises(ProviderListingNotFoundError):
            asyncio.run(provider.refresh("K-999"))


def test_admin_import_search_filters_by_intent():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "listings.jsonl"
        path.write_text("\n".join([
            json.dumps({
                "source_listing_id": "M-1", "title": "3BHK", "price": 8000000,
                "property_type": "apartment", "city": "Mumbai", "bedrooms": 3,
            }),
            json.dumps({
                "source_listing_id": "M-2", "title": "4BHK Villa", "price": 20000000,
                "property_type": "villa", "city": "Mumbai", "bedrooms": 4,
            }),
        ]), encoding="utf-8")
        provider = AdminImportProvider(file_path=str(path))
        results = asyncio.run(provider.search({"city": "Mumbai", "property_type": "villa"}))
        assert len(results) == 1
        assert results[0]["source_listing_id"] == "M-2"