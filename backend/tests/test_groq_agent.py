"""Unit contracts for the real AI gateway and the bounded tool agent."""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.ai.agent import GroqToolCallingAgent
from app.ai.gateway import AIConfigurationError, AIValidationError
from app.ai.providers.base import ChatResult, ProviderCapabilities
from app.ai.registry import ProviderEntry, ProviderRegistry
from app.ai.resilience import CircuitBreaker, ConcurrencyLimiter, ProviderMetrics
from app.ai.tool_registry import ToolRegistry
from app.core.config import settings


# ── Stubs ────────────────────────────────────────────────────────────────

class StubTransportProvider:
    """A provider whose HTTP status is scripted, for failure-path tests."""

    def __init__(self, name: str, status: int, payload: dict | None = None) -> None:
        self.name = name
        self.provider = name
        self.model = f"{name}-stub-model"
        self.status = status
        self.payload = payload or {}
        self.attempts = 0

    def chat(self, messages, tools, *, max_tokens: int, structured: bool = False,
             model: str | None = None) -> ChatResult:
        self.attempts += 1
        if self.status >= 400:
            request = httpx.Request("POST", "https://stub.invalid/v1/chat/completions")
            response = httpx.Response(self.status, json={"error": {"message": "stub failure"}})
            raise httpx.HTTPStatusError("stub", request=request, response=response)
        return ChatResult(
            message=__import__("app.ai.providers.base", fromlist=["ChatMessage"]).ChatMessage(
                content=self.payload.get("text", "ok"), tool_calls=[]),
            model=self.model,
            provider=self.name,
            latency_ms=1.0,
            total_tokens=1,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.name, model=self.model, chat=True,
                                    tool_calling=True, structured_output=True, cost_tier="free")


def _stub_entry(name: str, status: int, payload: dict | None = None) -> ProviderEntry:
    return ProviderEntry(name=name, provider=StubTransportProvider(name, status, payload),
                         configured=True, priority=0)


def _registry_with_entries(entries: list[ProviderEntry]) -> ProviderRegistry:
    """Build a registry without touching the real settings."""
    import threading

    registry = object.__new__(ProviderRegistry)
    registry.settings = settings
    registry.metrics = ProviderMetrics()
    registry.circuit = CircuitBreaker(failure_threshold=2, cooldown_seconds=999.0)
    registry.limiter = ConcurrencyLimiter(limit=2)
    registry._lock = threading.Lock()
    registry._entries = {entry.name: entry for entry in entries}
    return registry


def _registry_without_credentials() -> ProviderRegistry:
    import threading

    registry = object.__new__(ProviderRegistry)
    registry.settings = settings
    registry.metrics = ProviderMetrics()
    registry.circuit = CircuitBreaker()
    registry.limiter = ConcurrencyLimiter(limit=2)
    registry._lock = threading.Lock()
    registry._entries = {}
    return registry


class FakeProvider:
    name = "groq"

    def __init__(self, calls):
        self.calls = calls
        self.invocations = 0

    def generate_with_tools(self, messages, tools):
        self.invocations += 1
        calls = self.calls if self.invocations == 1 else []
        return {"message": {"content": "", "tool_calls": calls}, "latency_ms": 1.0, "model": "qwen/qwen3.8-27b"}

    def generate_structured(self, messages, schema_name, schema):
        return {"message": {"content": json.dumps({"answer": "Here are verified matches.", "property_ids": [101], "follow_up_suggestions": []})}, "latency_ms": 1.0, "model": "qwen/qwen3.8-27b"}


class FakeRegistry:
    def definitions(self):
        return [{"type": "function", "function": {"name": "search_properties", "parameters": {}}}]

    def execute(self, db, user, name, arguments):
        assert name == "search_properties"
        return {
            "total": 1,
            "parsed": {"raw_text": "3BHK in Hyderabad", "listing_type": "sale", "nearby_requirements": [], "lifestyle": [], "keywords": []},
            "results": [{"property_id": 101, "title": "Verified test home", "slug": "verified-test-home", "price": 8_500_000,
                         "city": "Hyderabad", "property_type": "apartment", "is_featured": False, "is_synthetic": True,
                         "verification_status": "unverified", "overall_score": 91, "component_scores": [], "positive_factors": ["Within requested budget"], "negative_factors": []}],
        }, 2.0


def test_registry_rejects_unknown_or_invalid_tool_arguments():
    registry = ToolRegistry()
    with pytest.raises(AIValidationError):
        registry.execute(None, None, "__import__", {})
    with pytest.raises(AIValidationError):
        registry.execute(None, None, "route", {"from_lat": "not-a-coordinate"})


def test_agent_returns_only_grounded_property_ids():
    tool_call = {"id": "tool-1", "function": {"name": "search_properties", "arguments": '{"query":"3BHK Hyderabad"}'}}
    result = GroqToolCallingAgent(None, object(), provider=FakeProvider([tool_call]), registry=FakeRegistry()).run("Find a 3BHK", [])
    assert result.provider == "groq"
    assert [row.property_id for row in result.results] == [101]
    assert result.citations[0].source_id == 101
    assert result.tool_calls[0].tool == "search_properties"


def test_gateway_raises_configuration_error_without_any_provider(monkeypatch):
    """No credential at all must be a clean configuration error, not a crash."""
    from app.ai.gateway import AIGateway

    monkeypatch.setattr(settings, "AI_PROVIDER_PRIORITY", "groq,gemini,openai")
    registry = _registry_without_credentials()
    gateway = AIGateway(registry)
    with pytest.raises(AIConfigurationError):
        gateway.generate_with_tools([{"role": "user", "content": "hello"}], [])


def test_gateway_maps_a_permanent_auth_error_without_retrying(monkeypatch):
    """A 401 is permanent: it must not be retried and must not fall back."""
    from app.ai.gateway import AIAuthenticationError, AIGateway

    entry = _stub_entry("groq", status=401)
    registry = _registry_with_entries([entry])
    gateway = AIGateway(registry)
    with pytest.raises(AIAuthenticationError):
        gateway.generate_with_tools([{"role": "user", "content": "hello"}], [])
    assert entry.provider.attempts == 1, "a permanent error must not be retried"


def test_gateway_falls_back_after_a_rate_limit(monkeypatch):
    """A 429 on the primary must move to the fallback without fabricating."""
    from app.ai.gateway import AIGateway

    primary = _stub_entry("groq", status=429)
    fallback = _stub_entry(
        "gemini", status=200,
        payload={"candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                 "usageMetadata": {"totalTokenCount": 3}},
    )
    registry = _registry_with_entries([primary, fallback])
    gateway = AIGateway(registry)

    result = gateway.generate_with_tools([{"role": "user", "content": "hello"}], [])
    assert result["provider"] == "gemini"
    assert result["message"]["content"] == "ok"
    assert primary.provider.attempts >= 1
    # The primary failure is recorded so the circuit breaker can open.
    assert registry.metrics.health("groq").rate_limited >= 1


def test_gateway_returns_an_honest_error_when_all_providers_fail():
    """Every provider failing must surface AIUnavailableError, never a guess."""
    from app.ai.gateway import AIUnavailableError, AIGateway

    primary = _stub_entry("groq", status=503)
    fallback = _stub_entry("gemini", status=500)
    gateway = AIGateway(_registry_with_entries([primary, fallback]))
    with pytest.raises(AIUnavailableError) as excinfo:
        gateway.generate_with_tools([{"role": "user", "content": "hello"}], [])
    assert "groq" in str(excinfo.value) and "gemini" in str(excinfo.value)


def test_gateway_opens_the_circuit_after_repeated_failures():
    from app.ai.gateway import AIUnavailableError, AIGateway

    entry = _stub_entry("groq", status=503)
    registry = _registry_with_entries([entry])
    gateway = AIGateway(registry)
    for _ in range(3):
        with pytest.raises(AIUnavailableError):
            gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
    assert registry.circuit.is_open("groq")
    # Once open, the provider is not attempted again until the cooldown ends.
    attempts_before = entry.provider.attempts
    with pytest.raises(AIUnavailableError):
        gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
    assert entry.provider.attempts == attempts_before
