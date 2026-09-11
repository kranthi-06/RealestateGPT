"""Unit contracts for the real Groq gateway and bounded tool agent."""
from __future__ import annotations

import json

import httpx
import pytest

from app.ai.agent import GroqToolCallingAgent
from app.ai.gateway import AIConfigurationError, AIValidationError, GroqProvider
from app.ai.tool_registry import ToolRegistry
from app.core.config import settings


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


def test_groq_gateway_maps_auth_and_configuration_errors(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "offline")
    with pytest.raises(AIConfigurationError):
        GroqProvider()
    monkeypatch.setattr(settings, "AI_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"message": "bad key"}}))
    from app.ai.gateway import AIAuthenticationError
    with pytest.raises(AIAuthenticationError):
        GroqProvider(transport=transport).generate_with_tools([{"role": "user", "content": "hello"}], [])
