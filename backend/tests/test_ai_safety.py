"""AI safety and authorization tests.

Guards the properties that make the assistant trustworthy:
* the tool registry is a closed allow-list — a model can never call arbitrary
  code or an unregistered tool;
* tools that write on behalf of a user always act on the authenticated user,
  never on an identity supplied by the caller;
* the rate limiter is enforced and refunds slots for requests that never
  reached the provider;
* the assistant endpoint requires authentication.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from fake_mongo import FakeDB

from app.ai import tools as ai_tools
from app.ai.gateway import AIValidationError
from app.ai.tool_registry import ToolRegistry
from app.core.ai_rate_limit import AIRateLimiter
from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.user import User

USER = User(id=4242, email="ai@example.test", full_name="AI", hashed_password="x", role="user")


@pytest.fixture(autouse=True)
def _clean_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def store() -> FakeDB:
    return FakeDB()


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


class TestToolRegistryIsClosed:
    # Handler names that are aliases of a registered model-facing tool name.
    _HANDLER_ALIASES = {"compare", "find_nearby_places", "calculate_route", "calculate_affordability"}

    def test_only_registered_tools_are_exposed(self, registry: ToolRegistry):
        registered = {tool.name: tool.handler_name for tool in registry._tools.values()}
        # Every handler the registry can reach exists in the application table
        # (a few are intentionally aliased to another registered name).
        handlers = set(registered.values())
        assert handlers - self._HANDLER_ALIASES <= {tool.name for tool in ai_tools.TOOLS}
        # A tool that writes for the user is registered and auth-gated.
        assert {"save_property", "unsave_property", "list_saved_properties"} <= set(registered)

    def test_unknown_tool_is_rejected(self, registry: ToolRegistry, store: FakeDB):
        with pytest.raises(AIValidationError):
            registry.execute(store, USER, "exec_python", "{}")

    def test_tool_name_cannot_smuggle_a_handler(self, registry: ToolRegistry, store: FakeDB):
        # A dotted / path-like name must not resolve to anything.
        for name in ("app.repositories.saved_repo", "__import__", "os.system"):
            with pytest.raises(AIValidationError):
                registry.execute(store, USER, name, "{}")

    def test_invalid_arguments_are_rejected(self, registry: ToolRegistry, store: FakeDB):
        with pytest.raises(AIValidationError):
            registry.execute(store, USER, "save_property", "{not json")
        with pytest.raises(AIValidationError):
            registry.execute(store, USER, "save_property", '{"property_id": "abc"}')


class TestUserScopedTools:
    """A tool must act on the authenticated user, never a caller-supplied id."""

    def _property(self, store: FakeDB, pid: int) -> None:
        from datetime import datetime, timezone

        store["properties"].insert_one({
            "_id": pid, "title": "AI Property", "slug": "ai-property", "price": 5_000_000.0,
            "currency": "INR", "property_type": "apartment", "listing_type": "sale",
            "city": "Hyderabad", "source": "t", "source_type": "admin",
            "verification_status": "verified", "is_active": True, "status": "active",
            "amenities": [], "images": [], "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })

    def test_saving_via_tool_targets_the_authenticated_user(self, store: FakeDB, registry: ToolRegistry):
        from app.core.security import get_optional_user

        self._property(store, 1001)
        result, _ = registry.execute(store, USER, "save_property", '{"property_id": 1001}')
        assert result["already_saved"] is False
        assert store["saved_properties"].find_one({"user_id": USER.id, "property_id": 1001})

        # A second save is idempotent and still scoped to this user.
        result, _ = registry.execute(store, USER, "save_property", '{"property_id": 1001}')
        assert result["already_saved"] is True

    def test_save_tool_requires_authentication(self, store: FakeDB, registry: ToolRegistry):
        with pytest.raises(AIValidationError):
            registry.execute(store, None, "save_property", '{"property_id": 1001}')

    def test_saved_list_only_returns_the_authenticated_users_rows(
        self, store: FakeDB, registry: ToolRegistry
    ):
        from datetime import datetime, timezone

        self._property(store, 1001)
        # A row belonging to a different user must never surface.
        store["saved_properties"].insert_one({
            "_id": 1, "user_id": 9999, "property_id": 1001,
            "notes": None, "created_at": datetime.now(timezone.utc),
        })
        store["saved_properties"].insert_one({
            "_id": 2, "user_id": USER.id, "property_id": 1001,
            "notes": None, "created_at": datetime.now(timezone.utc),
        })
        result, _ = registry.execute(store, USER, "list_saved_properties", "{}")
        assert result["total"] == 1
        assert result["results"][0]["property_id"] == 1001

    def test_affordability_uses_the_catalogue_price_not_a_supplied_one(
        self, store: FakeDB, registry: ToolRegistry
    ):
        self._property(store, 1001)
        result, _ = registry.execute(
            store, USER, "calculate_affordability",
            '{"monthly_income": 70000, "savings": 1200000, "property_id": 1001}',
        )
        # The price must be read from the record, not invented by the model.
        assert result["status"] == "ok"
        assert result["price_source"] == "catalogue_property_1001"
        assert result["property_assessment"]["property_price"] == 5_000_000.0

    def test_affordability_rejects_two_price_sources(self, store: FakeDB, registry: ToolRegistry):
        self._property(store, 1001)
        with pytest.raises(AIValidationError):
            registry.execute(
                store, USER, "calculate_affordability",
                '{"monthly_income": 70000, "property_id": 1001, "property_price": 5000000}',
            )

    def test_affordability_reports_an_unknown_property_honestly(
        self, store: FakeDB, registry: ToolRegistry
    ):
        result, _ = registry.execute(
            store, USER, "calculate_affordability",
            '{"monthly_income": 70000, "property_id": 424242}',
        )
        assert result["status"] == "not_found"


class TestAIRateLimiter:
    def test_limit_is_enforced(self):
        limiter = AIRateLimiter()
        from app.core.config import settings

        settings.RATE_LIMIT_ENABLED = True
        previous = settings.AI_RATE_LIMIT_REQUESTS
        settings.AI_RATE_LIMIT_REQUESTS = 3
        try:
            for _ in range(3):
                limiter.check("user:1")
            with pytest.raises(Exception):
                limiter.check("user:1")
            # A different account is unaffected.
            limiter.check("user:2")
        finally:
            settings.AI_RATE_LIMIT_REQUESTS = previous
            settings.RATE_LIMIT_ENABLED = False

    def test_unconsumed_slots_are_refunded(self):
        limiter = AIRateLimiter()
        from app.core.config import settings

        settings.RATE_LIMIT_ENABLED = True
        previous = settings.AI_RATE_LIMIT_REQUESTS
        settings.AI_RATE_LIMIT_REQUESTS = 2
        try:
            limiter.check("user:1")
            limiter.release("user:1", consumed=False)
            # Both slots are available again, so this does not raise.
            limiter.check("user:1")
            limiter.check("user:1")
        finally:
            settings.AI_RATE_LIMIT_REQUESTS = previous
            settings.RATE_LIMIT_ENABLED = False


class TestAssistantEndpointAuth:
    def test_assistant_requires_authentication(self, store: FakeDB):
        app.dependency_overrides[get_db] = lambda: store
        app.dependency_overrides.pop(get_current_user, None)
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/assistant", json={"message": "show me homes"}
            )
        assert response.status_code == 401

    def test_conversation_belonging_to_another_user_is_not_found(self, store: FakeDB):
        from datetime import datetime, timezone

        app.dependency_overrides[get_db] = lambda: store
        app.dependency_overrides[get_current_user] = lambda: USER
        store["conversations"].insert_one({
            "_id": 1, "user_id": 9999, "title": "not mine",
            "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        })
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/assistant",
                json={"message": "hello", "conversation_id": 1},
            )
        assert response.status_code == 404

    def test_conversations_list_is_scoped_to_the_user(self, store: FakeDB):
        from datetime import datetime, timezone

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
