"""Grounded-assistant orchestration tests.

The live Groq free tier is rate limited on this key, so the real provider
cannot be exercised repeatedly. These tests drive the actual agent, the
tool registry and the orchestrator against a real (in-memory) catalogue through
a fake provider that returns the same shapes Groq does — so the grounding and
authorization logic is genuinely covered rather than mocked away.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fake_mongo import FakeDB

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.agent import GroqToolCallingAgent  # noqa: E402
from app.ai.tool_registry import ToolRegistry  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.security import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402

USER = User(id=4242, email="agent@example.test", full_name="Agent", hashed_password="x", role="user")

# Three real catalogue records with real prices, areas and localities.
CATALOGUE = [
    {"_id": 2001, "title": "My Home Bhavan 2BHK Gachibowli", "slug": "my-home-2001",
     "price": 5_600_000.0, "area_sqft": 1160.0, "price_per_sqft": 4827.59,
     "bedrooms": 2, "bathrooms": 2, "city": "Hyderabad", "locality": "Gachibowli"},
    {"_id": 2002, "title": "Aparna Cyber Life 2BHK Nallagandla", "slug": "aparna-2002",
     "price": 5_900_000.0, "area_sqft": 1240.0, "price_per_sqft": 4758.06,
     "bedrooms": 2, "bathrooms": 2, "city": "Hyderabad", "locality": "Nallagandla"},
    {"_id": 2003, "title": "Rajapushpa Provincia 2BHK Kokapet", "slug": "rajapushpa-2003",
     "price": 6_400_000.0, "area_sqft": 1290.0, "price_per_sqft": 4961.24,
     "bedrooms": 2, "bathrooms": 2, "city": "Hyderabad", "locality": "Kokapet"},
]


class FakeProvider:
    """Returns Groq-shaped completions: one tool call, then a final answer."""

    name = "groq"

    def __init__(self, tool_name: str, arguments: dict) -> None:
        self.tool_name = tool_name
        self.arguments = arguments
        self.calls = 0

    def generate_with_tools(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {
                "message": {
                    "role": "assistant", "content": "",
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": self.tool_name,
                                     "arguments": json.dumps(self.arguments)},
                    }],
                },
                "latency_ms": 1.0,
            }
        return {"message": {"role": "assistant", "content": ""}, "latency_ms": 1.0}

    def generate_structured(self, messages, schema_name, schema):
        return {"message": {"role": "assistant", "content": json.dumps({
            "answer": "Two 2 BHK apartments in Hyderabad under 60 lakh are in the catalogue.",
            "property_ids": [2001, 2002],
            "follow_up_suggestions": ["Which has the lowest price per square foot?"],
        })}, "latency_ms": 1.0}


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def store() -> FakeDB:
    db = FakeDB()
    now = datetime.now(timezone.utc)
    for row in CATALOGUE:
        db["properties"].insert_one({
            **row,
            "currency": "INR", "property_type": "apartment", "listing_type": "sale",
            "source": "test", "source_type": "admin", "verification_status": "verified",
            "is_active": True, "status": "active", "is_synthetic": False,
            "amenities": [], "images": [], "created_at": now, "updated_at": now,
            "last_verified_at": now, "state": "Telangana",
        })
    return db


def _agent(store: FakeDB, tool: str, arguments: dict) -> Any:
    provider = FakeProvider(tool, arguments)
    return GroqToolCallingAgent(store, USER, provider=provider, registry=ToolRegistry())


class TestGroundedSearch:
    def test_results_are_real_catalogue_rows(self, store: FakeDB):
        result = _agent(store, "search_properties",
                        {"city": "Hyderabad", "bedrooms": 2, "max_price": 6_000_000}).run(
            "Find 2 BHK apartments in Hyderabad under 60 lakh", [])
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool == "search_properties"
        # Only ids that exist in the catalogue, never an invented listing.
        assert {r.property_id for r in result.results} <= {row["_id"] for row in CATALOGUE}
        assert result.results, "the search returns matching listings"
        assert all(r.price > 0 for r in result.results)
        assert result.answer.strip()


class TestAffordabilityUsesTheCataloguePrice:
    def test_asking_price_is_resolved_from_the_record(self, store: FakeDB):
        result = _agent(store, "calculate_affordability", {
            "monthly_income": 70000, "savings": 1200000,
            "down_payment": 1000000, "property_id": 2001}).run(
            "Can I afford the first property?", [])
        assert result.tool_calls[0].tool == "calculate_affordability"

        # Re-run the tool directly so the numeric result can be asserted.
        registry = ToolRegistry()
        output, _ = registry.execute(store, USER, "calculate_affordability", json.dumps({
            "monthly_income": 70000, "savings": 1200000,
            "down_payment": 1000000, "property_id": 2001}))
        assert output["status"] == "ok"
        assert output["price_source"] == "catalogue_property_2001"
        assert output["property_assessment"]["property_price"] == 5_600_000.0


class TestAgentWritesForTheAuthenticatedUser:
    def test_saving_writes_a_row_for_that_user_only(self, store: FakeDB):
        _agent(store, "save_property", {"property_id": 2001}).run("Save the cheapest one", [])
        assert store["saved_properties"].find_one({"user_id": USER.id, "property_id": 2001})
        assert store["saved_properties"].find_one({"user_id": 9999}) is None

    def test_saved_list_never_exposes_another_users_rows(self, store: FakeDB):
        store["saved_properties"].insert_one({
            "_id": 500, "user_id": 4242, "property_id": 2001, "notes": None,
            "created_at": datetime.now(timezone.utc)})
        # A row belonging to somebody else must not leak into the tool output.
        store["saved_properties"].insert_one({
            "_id": 501, "user_id": 9999, "property_id": 2002, "notes": None,
            "created_at": datetime.now(timezone.utc)})

        registry = ToolRegistry()
        output, _ = registry.execute(store, USER, "list_saved_properties", "{}")
        assert output["total"] == 1
        assert output["results"][0]["property_id"] == 2001


class TestEndpointAuthorization:
    def test_assistant_requires_authentication(self, store: FakeDB):
        app.dependency_overrides[get_db] = lambda: store
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app) as client:
            assert client.post("/api/v1/ai/assistant",
                               json={"message": "show me homes"}).status_code == 401

    def test_another_users_conversation_is_not_found(self, store: FakeDB):
        app.dependency_overrides[get_db] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: USER
        store["conversations"].insert_one({
            "_id": 1, "user_id": 9999, "title": "not mine",
            "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})
        with TestClient(app) as client:
            assert client.post(
                "/api/v1/ai/assistant", json={"message": "hello", "conversation_id": 1}
            ).status_code == 404

    def test_conversations_are_scoped_to_the_user(self, store: FakeDB):
        app.dependency_overrides[get_db] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: USER
        now = datetime.now(timezone.utc)
        store["conversations"].insert_one({
            "_id": 1, "user_id": 9999, "title": "theirs", "created_at": now, "updated_at": now})
        store["conversations"].insert_one({
            "_id": 2, "user_id": USER.id, "title": "mine", "created_at": now, "updated_at": now})
        with TestClient(app) as client:
            rows = client.get("/api/v1/ai/conversations").json()
        assert [r["id"] for r in rows] == [2]
