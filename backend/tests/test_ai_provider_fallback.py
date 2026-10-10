"""Multi-provider fallback, resilience and format-translation tests.

Every failure path is mocked: no real quota is consumed to test a 429, a
timeout, an invalid key or a full outage.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx
import pytest

from app.ai.gateway import (
    AIConfigurationError,
    AIGateway,
    AIUnavailableError,
    AIValidationError,
    AITimeoutError,
)
from app.ai.providers.base import ChatMessage, ChatResult, ProviderCapabilities
from app.ai.providers.gemini import (
    _clean_schema,
    to_gemini_contents,
    to_gemini_tools,
    to_openai_tool_calls,
)
from app.ai.registry import VERIFIED_MODELS, ProviderEntry, ProviderRegistry
from app.ai.resilience import (
    CircuitBreaker,
    ConcurrencyLimiter,
    RetryPolicy,
    backoff_delay,
    is_permanent_status,
    is_retryable_status,
)
from app.core.config import settings


# â”€â”€ stubs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ScriptedProvider:
    """A provider whose behaviour is scripted per attempt."""

    def __init__(self, name: str, script: list[Any]) -> None:
        self.name = name
        self.provider = name
        self.model = f"{name}-model"
        self.script = script
        self.attempts = 0
        self.last_model: str | None = None
        self.last_max_tokens: int | None = None

    def chat(self, messages, tools, *, max_tokens: int, structured: bool = False,
             model: str | None = None) -> ChatResult:
        self.last_model = model
        self.last_max_tokens = max_tokens
        index = min(self.attempts, len(self.script) - 1)
        self.attempts += 1
        outcome = self.script[index]
        if isinstance(outcome, Exception):
            raise outcome
        status, payload = outcome
        if status >= 400:
            request = httpx.Request("POST", "https://stub.invalid/v1/chat/completions")
            response = httpx.Response(status, json={"error": {"message": "stub"}})
            raise httpx.HTTPStatusError("stub", request=request, response=response)
        return ChatResult(
            message=ChatMessage(content=payload.get("text", "ok"),
                                 tool_calls=payload.get("tool_calls", [])),
            model=model or self.model, provider=self.name, latency_ms=1.0, total_tokens=1,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.name, model=self.model, chat=True,
                                    tool_calling=True, structured_output=True, cost_tier="free")


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://stub.invalid/v1/chat/completions")
    response = httpx.Response(status, json={"error": {"message": "stub"}})
    return httpx.HTTPStatusError("stub", request=request, response=response)


def _registry(entries: list[ProviderEntry], *, threshold: int = 3,
              cooldown: float = 60.0) -> ProviderRegistry:
    registry = object.__new__(ProviderRegistry)
    registry.settings = settings
    registry.metrics = __import__(
        "app.ai.resilience", fromlist=["ProviderMetrics"]).ProviderMetrics()
    registry.circuit = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=cooldown)
    registry.limiter = ConcurrencyLimiter(limit=4)
    registry._lock = threading.Lock()
    registry._entries = {entry.name: entry for entry in entries}
    return registry


def _entry(provider: ScriptedProvider, priority: int = 0,
           capabilities: ProviderCapabilities | None = None) -> ProviderEntry:
    return ProviderEntry(name=provider.name, provider=provider, configured=True,
                         priority=priority, capabilities=capabilities)


# â”€â”€ error classification â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestErrorClassification:
    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    def test_permanent_statuses_are_not_retried(self, status):
        assert is_permanent_status(status) is True
        assert is_retryable_status(status) is False

    @pytest.mark.parametrize("status", [408, 409, 425, 429, 500, 502, 503, 504])
    def test_retryable_statuses(self, status):
        assert is_retryable_status(status) is True
        assert is_permanent_status(status) is False


# â”€â”€ retry policy â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestRetryPolicy:
    def test_backoff_grows_and_is_capped(self):
        assert backoff_delay(1, 0.5, 8.0) <= 0.5
        assert backoff_delay(2, 0.5, 8.0) <= 1.0
        assert backoff_delay(3, 0.5, 8.0) <= 2.0
        # A large attempt number is capped, never unbounded.
        assert backoff_delay(50, 0.5, 8.0) <= 8.0

    def test_backoff_is_jittered(self):
        values = {round(backoff_delay(4, 1.0, 30.0), 6) for _ in range(50)}
        assert len(values) > 1, "backoff must include jitter, not a fixed delay"

    def test_policy_has_one_fewer_delay_than_attempts(self):
        policy = RetryPolicy(max_attempts=3, base_seconds=0.01, max_seconds=0.02)
        assert len(policy.delays()) == 2

    def test_a_single_attempt_never_sleeps(self):
        policy = RetryPolicy(max_attempts=1, base_seconds=5.0, max_seconds=5.0)
        assert policy.delays() == []


# â”€â”€ circuit breaker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestCircuitBreaker:
    def test_opens_after_the_threshold_and_recovers(self):
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
        breaker.record_failure("p")
        assert breaker.is_open("p") is False
        breaker.record_failure("p")
        assert breaker.is_open("p") is True
        time.sleep(0.06)
        assert breaker.is_open("p") is False, "cooldown elapsed allows a trial"

    def test_success_resets_the_failure_count(self):
        breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
        breaker.record_failure("p")
        breaker.record_failure("p")
        breaker.record_success("p")
        for _ in range(2):
            breaker.record_failure("p")
        assert breaker.is_open("p") is False

    def test_remaining_cooldown_counts_down(self):
        breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=30.0)
        breaker.record_failure("p")
        remaining = breaker.remaining_cooldown("p")
        assert 0 < remaining <= 30


# â”€â”€ concurrency limiter â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestConcurrencyLimiter:
    def test_only_n_slots_are_granted(self):
        limiter = ConcurrencyLimiter(limit=2)
        with limiter.slot():
            with limiter.slot():
                acquired = limiter._semaphore.acquire(blocking=False)
                assert acquired is False, "a third caller must wait"


# â”€â”€ gateway fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestGatewayFallback:
    def test_primary_success_never_touches_the_fallback(self):
        primary = ScriptedProvider("groq", [(200, {"text": "from groq"})])
        fallback = ScriptedProvider("gemini", [(200, {"text": "from gemini"})])
        gateway = AIGateway(_registry([_entry(primary, 0), _entry(fallback, 1)]))

        result = gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
        assert result["provider"] == "groq"
        assert fallback.attempts == 0

    def test_429_on_primary_falls_through(self):
        primary = ScriptedProvider("groq", [(429, {})])
        fallback = ScriptedProvider("gemini", [(200, {"text": "from gemini"})])
        gateway = AIGateway(_registry([
            _entry(primary, 0, ProviderCapabilities(
                provider="groq", model="m", chat=True, tool_calling=True,
                structured_output=True, cost_tier="free")),
            _entry(fallback, 1, ProviderCapabilities(
                provider="gemini", model="m", chat=True, tool_calling=True,
                structured_output=True, cost_tier="free")),
        ]))

        result = gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
        assert result["provider"] == "gemini"
        assert primary.attempts >= 1

    def test_a_single_transient_failure_is_retried_on_the_same_provider(self):
        # One 503 then success: the retry stays on the same provider.
        provider = ScriptedProvider("groq", [(503, {}), (200, {"text": "recovered"})])
        entry = _entry(provider, 0)
        registry = _registry([entry])
        # Force a single attempt so the retry is observable without sleeping.
        registry.settings = settings
        gateway = AIGateway(registry)
        gateway.retry = RetryPolicy(max_attempts=2, base_seconds=0.001, max_seconds=0.002)

        result = gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
        assert provider.attempts == 2
        assert result["message"]["content"] == "recovered"

    def test_a_permanent_auth_error_does_not_fall_back(self):
        primary = ScriptedProvider("groq", [_http_error(401)])
        fallback = ScriptedProvider("gemini", [(200, {"text": "from gemini"})])
        gateway = AIGateway(_registry([_entry(primary, 0), _entry(fallback, 1)]))

        with pytest.raises(Exception) as excinfo:
            gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
        assert "credential" in str(excinfo.value)
        assert fallback.attempts == 0, "a bad key must not be retried elsewhere"
        assert primary.attempts == 1, "a permanent error must not be retried"

    def test_a_timeout_falls_through(self):
        primary = ScriptedProvider("groq", [httpx.ReadTimeout("timeout")])
        fallback = ScriptedProvider("gemini", [(200, {"text": "from gemini"})])
        gateway = AIGateway(_registry([_entry(primary, 0), _entry(fallback, 1)]))

        result = gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
        assert result["provider"] == "gemini"

    def test_all_providers_failing_raises_unavailable(self):
        gateway = AIGateway(_registry([
            _entry(ScriptedProvider("groq", [_http_error(503)]), 0),
            _entry(ScriptedProvider("gemini", [_http_error(500)]), 1),
        ]))
        with pytest.raises(AIUnavailableError) as excinfo:
            gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
        message = str(excinfo.value)
        assert "groq" in message and "gemini" in message
        # The error is an honest failure, never a fabricated answer.
        assert "unavailable" in message.lower()

    def test_no_configured_provider_is_a_configuration_error(self):
        gateway = AIGateway(_registry([]))
        with pytest.raises(AIConfigurationError):
            gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])

    def test_an_open_circuit_short_circuits_the_attempt(self):
        provider = ScriptedProvider("groq", [(200, {"text": "ok"})])
        entry = _entry(provider, 0)
        registry = _registry([entry], threshold=1, cooldown=999.0)
        registry.circuit.record_failure("groq")
        gateway = AIGateway(registry)

        with pytest.raises(AIUnavailableError):
            gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
        assert provider.attempts == 0

    def test_a_paid_provider_is_skipped_unless_authorised(self):
        paid = _entry(ScriptedProvider("openai", [(200, {"text": "paid"})]), 0,
                      ProviderCapabilities(provider="openai", model="m", chat=True,
                                           tool_calling=True, structured_output=True,
                                           input_cost_per_million=0.15,
                                           output_cost_per_million=0.60,
                                           cost_tier="paid"))
        free = _entry(ScriptedProvider("gemini", [(200, {"text": "free"})]), 1,
                      ProviderCapabilities(provider="gemini", model="m", chat=True,
                                           tool_calling=True, structured_output=True,
                                           cost_tier="free"))
        gateway = AIGateway(_registry([paid, free]))

        result = gateway.generate_with_tools([{"role": "user", "content": "hi"}], [])
        assert result["provider"] == "gemini", "free capacity is preferred"
        assert paid.provider.attempts == 0


# â”€â”€ capability gating â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def test_a_transient_probe_failure_does_not_disqualify_the_provider(self):
        """A 429 during the capability probe is not a capability fact."""
        from app.ai.gateway import AIGateway

        # Groq's probe failed transiently -> chat/tools all False, error set.
        rate_limited = _entry(
            ScriptedProvider("groq", [_http_error(429)]), 0,
            ProviderCapabilities(provider="groq", model="m", chat=False,
                                 tool_calling=False, structured_output=False,
                                 error="rate limited or quota exhausted"))
        # Gemini is healthy.
        healthy = _entry(
            ScriptedProvider("gemini", [(200, {"text": "from gemini"})]), 1,
            ProviderCapabilities(provider="gemini", model="m", chat=True,
                                 tool_calling=True, structured_output=True,
                                 cost_tier="free"))
        gateway = AIGateway(_registry([rate_limited, healthy]))

        result = gateway.generate_with_tools(
            [{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "f"}}]
        )
        # Both were eligible; the healthy one answered.
        assert result["provider"] == "gemini"
        assert rate_limited.provider.attempts >= 1, "a transient probe failure must not exclude a provider"

    def test_a_genuine_capability_gap_still_excludes_the_provider(self):
        from app.ai.gateway import AIGateway

        # A completed probe (no error) that genuinely lacks tool calling.
        no_tools = _entry(
            ScriptedProvider("groq", [(200, {"text": "x"})]), 0,
            ProviderCapabilities(provider="groq", model="m", chat=True,
                                 tool_calling=False, structured_output=True,
                                 cost_tier="free"))
        with_tools = _entry(
            ScriptedProvider("gemini", [(200, {"text": "y"})]), 1,
            ProviderCapabilities(provider="gemini", model="m", chat=True,
                                 tool_calling=True, structured_output=True,
                                 cost_tier="free"))
        gateway = AIGateway(_registry([no_tools, with_tools]))

        result = gateway.generate_with_tools(
            [{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "f"}}]
        )
        assert result["provider"] == "gemini"
        assert no_tools.provider.attempts == 0
    def test_a_provider_without_tool_calling_is_not_used_for_tools(self):
        no_tools = _entry(ScriptedProvider("groq", [(200, {"text": "x"})]), 0,
                          ProviderCapabilities(provider="groq", model="m", chat=True,
                                               tool_calling=False, structured_output=True,
                                               cost_tier="free"))
        with_tools = _entry(ScriptedProvider("gemini", [(200, {"text": "y"})]), 1,
                            ProviderCapabilities(provider="gemini", model="m", chat=True,
                                                 tool_calling=True, structured_output=True,
                                                 cost_tier="free"))
        gateway = AIGateway(_registry([no_tools, with_tools]))

        result = gateway.generate_with_tools(
            [{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "f"}}]
        )
        assert result["provider"] == "gemini"
        assert no_tools.provider.attempts == 0

    def test_a_provider_without_structured_output_is_not_used_for_json(self):
        no_json = _entry(ScriptedProvider("groq", [(200, {"text": "x"})]), 0,
                         ProviderCapabilities(provider="groq", model="m", chat=True,
                                              tool_calling=True, structured_output=False,
                                              cost_tier="free"))
        with_json = _entry(ScriptedProvider("gemini", [(200, {"text": "{}"})]), 1,
                           ProviderCapabilities(provider="gemini", model="m", chat=True,
                                                tool_calling=True, structured_output=True,
                                                cost_tier="free"))
        gateway = AIGateway(_registry([no_json, with_json]))

        result = gateway.generate_structured(
            [{"role": "user", "content": "hi"}], "schema", {"type": "object"})
        assert result["provider"] == "gemini"
        assert no_json.provider.attempts == 0


# â”€â”€ Gemini format translation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_thought_signature_is_echoed_on_the_part():
    """Gemini 3.x rejects a follow-up unless the signature is on the Part."""
    contents, _ = to_gemini_contents([
        {"role": "user", "content": "find homes"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "gemini-0", "type": "function", "function": {
                "name": "search_properties",
                "arguments": '{"city": "Hyderabad"}',
                "thought_signature": "SIGNATURE-XYZ"}},
        ]},
    ])
    part = contents[1]["parts"][0]
    assert part["functionCall"]["name"] == "search_properties"
    # The signature is a sibling of functionCall, never a field inside it.
    assert part["thoughtSignature"] == "SIGNATURE-XYZ"
    assert "thoughtSignature" not in part["functionCall"]

def test_thought_signature_survives_the_round_trip():
    parts = [{"functionCall": {"name": "search_properties", "args": {"city": "Hyderabad"}},
              "thoughtSignature": "SIG-123"}]
    calls = to_openai_tool_calls(parts)
    assert calls[0]["function"]["thought_signature"] == "SIG-123"

    contents, _ = to_gemini_contents([
        {"role": "user", "content": "find homes"},
        {"role": "assistant", "content": "", "tool_calls": calls},
    ])
    assert contents[1]["parts"][0]["thoughtSignature"] == "SIG-123"

def test_a_tool_call_without_a_signature_still_translates():
    contents, _ = to_gemini_contents([
        {"role": "user", "content": "find homes"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c", "function": {"name": "search_properties", "arguments": "{}"}},
        ]},
    ])
    part = contents[1]["parts"][0]
    assert "thoughtSignature" not in part
    assert part["functionCall"]["args"] == {}


class TestToolPayloadBounds:
    """An oversized tool result must be truncated, not fail the request."""

    def test_an_oversized_payload_is_truncated(self):
        from app.ai.agent import MAX_TOOL_PAYLOAD_CHARS, _bounded_tool_payload

        payload = {"results": [{"i": i, "text": "x" * 500} for i in range(100)]}
        bounded = _bounded_tool_payload(payload)
        assert len(bounded) <= MAX_TOOL_PAYLOAD_CHARS + 32
        assert bounded.endswith("[truncated]")

    def test_a_small_payload_is_untouched(self):
        from app.ai.agent import _bounded_tool_payload

        small = {"total": 3, "results": []}
        assert _bounded_tool_payload(small) == json.dumps(small, separators=(",", ":"))

    def test_an_unserializable_payload_degrades_gracefully(self):
        from app.ai.agent import _bounded_tool_payload

        class NotSerializable:
            pass

        result = _bounded_tool_payload({"obj": NotSerializable()}, )
        assert "unserializable" in result or "obj" in result


class TestCapabilityAwareTier:
    """Complex work uses the verified strong model; simple work stays fast."""

    def _entry(self, model: str) -> ProviderEntry:
        provider = ScriptedProvider("groq", [(200, {"text": "ok"})])
        provider.model = model
        return _entry(provider, 0, ProviderCapabilities(
            provider="groq", model=model, chat=True, tool_calling=True,
            structured_output=True, cost_tier="free"))

    def test_complex_tier_uses_the_strong_model(self):
        from app.ai.gateway import AIGateway

        entry = self._entry(VERIFIED_MODELS["groq"]["fast"])
        gateway = AIGateway(_registry([entry]))
        gateway.chat([{"role": "user", "content": "analyse this investment"}], [],
                     complexity="complex")
        assert entry.provider.last_model == VERIFIED_MODELS["groq"]["complex"], (
            "complex work must use the verified strong model"
        )

    def test_fast_tier_uses_the_provider_default(self):
        from app.ai.gateway import AIGateway

        entry = self._entry("qwen/qwen3.8-27b")
        gateway = AIGateway(_registry([entry]))
        gateway.chat([{"role": "user", "content": "hi"}], [], complexity="fast")
        assert entry.provider.last_model is None

    def test_complex_tier_raises_the_token_budget(self):
        """The strong reasoning model needs headroom or it returns empty text."""
        from app.ai.gateway import AIGateway

        entry = self._entry("qwen/qwen3.8-27b")
        gateway = AIGateway(_registry([entry]))
        gateway.chat([{"role": "user", "content": "x"}], [], complexity="complex")
        assert entry.provider.last_max_tokens >= 2000, (
            f"complex work needs >=2000 output tokens, got {entry.provider.last_max_tokens}"
        )

    def test_fast_tier_keeps_the_configured_budget(self):
        from app.ai.gateway import AIGateway

        entry = self._entry("qwen/qwen3.8-27b")
        gateway = AIGateway(_registry([entry]))
        gateway.chat([{"role": "user", "content": "x"}], [], complexity="fast")
        assert entry.provider.last_max_tokens == settings.AI_MAX_TOKENS


class TestGeminiTranslation:
    def test_system_messages_become_a_system_instruction(self):
        contents, system = to_gemini_contents([
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ])
        assert system == "Be concise."
        assert contents == [{"role": "user", "parts": [{"text": "Hello"}]}]

    def test_assistant_text_maps_to_the_model_role(self):
        contents, _ = to_gemini_contents([
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "Thanks"},
        ])
        assert contents[1] == {"role": "model", "parts": [{"text": "Hello"}]}

    def test_tool_calls_become_a_described_call_without_a_signature(self):
        """An unsigned (foreign-provider) call is text, never a functionCall."""
        contents, _ = to_gemini_contents([
            {"role": "user", "content": "weather?"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'}},
            ]},
        ])
        part = contents[1]["parts"][0]
        assert "functionCall" not in part
        assert "get_weather" in part["text"]
        assert "Paris" in part["text"]

    def test_a_signed_tool_call_stays_a_function_call(self):
        contents, _ = to_gemini_contents([
            {"role": "user", "content": "weather?"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {
                    "name": "get_weather", "arguments": '{"city":"Paris"}',
                    "thought_signature": "SIG-1"}},
            ]},
        ])
        assert contents[1]["parts"][0]["functionCall"] == {
            "name": "get_weather", "args": {"city": "Paris"}}

    def test_tool_results_become_function_response_parts(self):
        contents, _ = to_gemini_contents([
            {"role": "user", "content": "weather?"},
            {"role": "tool", "name": "get_weather", "content": "18C"},
        ])
        assert contents[1]["parts"][0]["functionResponse"]["name"] == "get_weather"
        assert "18C" in str(contents[1]["parts"][0]["functionResponse"]["response"])

    def test_a_leading_model_turn_is_dropped(self):
        contents, _ = to_gemini_contents([
            {"role": "assistant", "content": "stale"},
            {"role": "user", "content": "Hi"},
        ])
        assert contents[0]["role"] == "user"

    def test_an_empty_message_list_still_produces_a_user_turn(self):
        contents, _ = to_gemini_contents([])
        assert contents == [{"role": "user", "parts": [{"text": ""}]}]

    def test_tool_definitions_are_translated(self):
        tools = [{"type": "function", "function": {
            "name": "get_weather", "description": "Weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                           "additionalProperties": False, "required": ["city"]}}}]
        declarations = to_gemini_tools(tools)[0]["functionDeclarations"]
        assert declarations[0]["name"] == "get_weather"
        # OpenAI-only keywords Gemini rejects are stripped.
        assert "additionalProperties" not in declarations[0]["parameters"]

    def test_function_call_parts_round_trip_to_openai_tool_calls(self):
        parts = [{"functionCall": {"name": "get_weather", "args": {"city": "Paris"}}}]
        calls = to_openai_tool_calls(parts)
        assert calls[0]["function"]["name"] == "get_weather"
        assert json.loads(calls[0]["function"]["arguments"]) == {"city": "Paris"}

    def test_no_tools_produces_an_empty_declaration_list(self):
        assert to_gemini_tools([]) == []

    def test_malformed_tool_arguments_do_not_crash(self):
        contents, _ = to_gemini_contents([
            {"role": "user", "content": "x"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c", "type": "function", "function": {
                    "name": "f", "arguments": "not json", "thought_signature": "SIG"}},
            ]},
        ])
        assert contents[1]["parts"][0]["functionCall"]["args"] == {}

# -- Gemini tool-schema cleaning ------------------------------------------

def test_a_tool_call_without_a_signature_still_translates():
    """A Groq-originated tool call must not be sent as a functionCall to Gemini."""
    contents, _ = to_gemini_contents([
        {"role": "user", "content": "find homes"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c", "function": {"name": "search_properties",
                                     "arguments": '{"city": "Hyderabad"}'}},
        ]},
    ])
    part = contents[1]["parts"][0]
    assert "functionCall" not in part, "an unsigned call must not be a functionCall"
    assert "search_properties" in part["text"]
    assert "Hyderabad" in part["text"]


class TestGeminiSchemaCleaning:
    """Pydantic emits keywords Gemini's OpenAPI subset rejects with HTTP 400."""

    def _declarations(self) -> list[dict]:
        from app.ai.tool_registry import ToolRegistry

        return to_gemini_tools(ToolRegistry().definitions())[0]["functionDeclarations"]

    def test_every_required_field_survives(self):
        """The earlier bug dropped every field: ``properties`` is a name map."""
        for declaration in self._declarations():
            parameters = declaration.get("parameters")
            if not parameters:
                continue
            required = parameters.get("required", [])
            properties = parameters.get("properties", {})
            for name in required:
                assert name in properties, (
                    f"{declaration['name']}: required {name!r} lost its definition"
                )

    def test_unsupported_keywords_are_removed(self):
        for declaration in self._declarations():
            parameters = declaration.get("parameters") or {}
            for field in (parameters.get("properties") or {}).values():
                assert "exclusiveMinimum" not in field
                assert "exclusiveMaximum" not in field
                assert "default" not in field
                assert "additionalProperties" not in field

    def test_optional_fields_become_nullable(self):
        schema = _clean_schema({
            "type": "object",
            "properties": {"city": {"anyOf": [{"type": "string"}, {"type": "null"}],
                                    "default": None}},
            "required": [],
        })
        assert schema["properties"]["city"]["nullable"] is True
        assert schema["properties"]["city"]["type"] == "string"

    def test_bounds_are_preserved(self):
        schema = _clean_schema({
            "type": "object",
            "properties": {"n": {"exclusiveMinimum": 0, "maximum": 20, "type": "integer"}},
        })
        assert schema["properties"]["n"]["minimum"] == 0
        assert schema["properties"]["n"]["maximum"] == 20

    def test_non_null_any_of_is_kept(self):
        schema = _clean_schema({
            "type": "object",
            "properties": {"v": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
        })
        assert schema["properties"]["v"]["anyOf"]

    def test_real_tool_schemas_are_usable(self):
        from app.ai.tool_registry import ToolRegistry

        declarations = self._declarations()
        assert len(declarations) == len(ToolRegistry().definitions())
        for declaration in declarations:
            parameters = declaration.get("parameters")
            if parameters:
                assert parameters.get("type") == "object"
                assert isinstance(parameters.get("properties", {}), dict)
