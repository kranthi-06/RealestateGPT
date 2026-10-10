"""OpenAI-compatible providers (Groq and OpenAI).

Both expose ``POST {base}/chat/completions`` with the same request and response
shape, so one adapter serves both; only the base URL, key and model differ.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.ai.providers.base import ChatMessage, ChatResult, ProviderCapabilities

logger = logging.getLogger(__name__)

USER_AGENT = "RealEstateGPT/1.0 (+https://realestate-gpt-inky.vercel.app)"

#: The capability probe must ask for enough tokens for a thinking model to
#: finish its internal reasoning AND emit an answer; a tiny budget makes a
#: healthy model look broken (finishReason=MAX_TOKENS with empty content).
PROBE_MAX_TOKENS = 512

# Published list prices (USD per 1M tokens). Used only for the cost estimate so
# free-tier capacity is never misreported as spend. Overridable per deployment
# through the provider registry when a provider changes its pricing.
PUBLISHED_PRICING: dict[str, dict[str, float]] = {
    "groq": {"input": 0.0, "output": 0.0},            # free tier capacity
    "openai": {"input": 0.15, "output": 0.60},        # gpt-4o-mini list price
}


class OpenAICompatibleProvider:
    """A provider that speaks the OpenAI chat-completions dialect."""

    name = "openai_compatible"

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        pricing: dict[str, float] | None = None,
        max_output_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.name = provider
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.pricing = pricing or PUBLISHED_PRICING.get(provider, {"input": 0.0, "output": 0.0})
        self.max_output_tokens = max_output_tokens

    # â”€â”€ request â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _payload(self, messages: list[dict], tools: list[dict], max_tokens: int,
                 structured: bool, model: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.1,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if structured:
            # json_object mode; the caller supplies the schema in the prompt and
            # Pydantic validates whatever comes back.
            payload["response_format"] = {"type": "json_object"}
        return payload

    def chat(self, messages: list[dict], tools: list[dict], *, max_tokens: int,
             structured: bool = False, model: str | None = None) -> ChatResult:
        effective_model = model or self.model
        started = time.perf_counter()
        with httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds),
            transport=self.transport,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=self._payload(messages, tools, max_tokens, structured, effective_model),
            )
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        if response.status_code >= 400:
            # Never echo the body: a provider error can contain the request.
            logger.error(
                "ai_provider_http_error provider=%s model=%s status=%s",
                self.provider, effective_model, response.status_code,
            )
            response.raise_for_status()

        try:
            body = response.json()
            raw_message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"{self.provider} returned an invalid completion") from exc

        usage = body.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        message = ChatMessage(
            content=raw_message.get("content") or "",
            tool_calls=list(raw_message.get("tool_calls") or []),
            raw={"id": body.get("id"), "finish_reason": (body.get("choices") or [{}])[0].get("finish_reason")},
        )
        return ChatResult(
            message=message,
            model=effective_model,
            provider=self.provider,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(usage.get("total_tokens") or (prompt_tokens + completion_tokens)),
            estimated_cost_usd=self._cost(prompt_tokens, completion_tokens),
        )

    def _cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens * self.pricing.get("input", 0.0)
            + completion_tokens * self.pricing.get("output", 0.0)
        ) / 1_000_000

    # â”€â”€ capability probe â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def capabilities(self) -> ProviderCapabilities:
        caps = ProviderCapabilities(
            provider=self.provider,
            model=self.model,
            max_output_tokens=self.max_output_tokens,
            input_cost_per_million=self.pricing.get("input", 0.0),
            output_cost_per_million=self.pricing.get("output", 0.0),
        )
        caps.cost_tier = (
            "free" if caps.input_cost_per_million == 0 and caps.output_cost_per_million == 0
            else "paid"
        )
        started = time.perf_counter()
        try:
            result = self.chat(
                [{"role": "user", "content": "Reply with the single word: ok"}],
                [], max_tokens=PROBE_MAX_TOKENS,
            )
            caps.chat = bool(result.message.content.strip())
        except Exception as exc:  # noqa: BLE001 - a probe must never raise
            caps.error = _safe_error(exc)
            return caps
        caps.latency_ms = round((time.perf_counter() - started) * 1000, 1)

        # Tool calling.
        try:
            result = self.chat(
                [{"role": "user", "content": "What is the weather in Paris? Use the tool."}],
                [_weather_tool()], max_tokens=PROBE_MAX_TOKENS,
            )
            caps.tool_calling = bool(result.message.tool_calls)
        except Exception as exc:  # noqa: BLE001
            caps.tool_calling = False

        # Structured output.
        try:
            self.chat(
                [{"role": "user", "content": 'Return JSON with a "status" key set to "ok".'}],
                [], max_tokens=PROBE_MAX_TOKENS, structured=True,
            )
            caps.structured_output = True
        except Exception as exc:  # noqa: BLE001
            caps.structured_output = False
        return caps


def _weather_tool() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }


def _safe_error(exc: Exception) -> str:
    """A short, credential-free description of a probe failure."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return "authentication failed (check the API key)"
    if status == 429:
        return "rate limited or quota exhausted"
    if status == 404:
        return "model not available for this key"
    if status is not None:
        return f"provider returned HTTP {status}"
    return f"{type(exc).__name__}"
