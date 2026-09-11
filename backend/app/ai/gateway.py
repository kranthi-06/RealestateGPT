"""Small, provider-isolated Groq OpenAI-compatible gateway."""
from __future__ import annotations

import time
from typing import Any, Protocol

import httpx

from app.core.config import settings


class AIError(RuntimeError):
    code = "AI_PROVIDER_ERROR"
    status_code = 502


class AIConfigurationError(AIError):
    code, status_code = "AI_CONFIGURATION_ERROR", 503


class AIAuthenticationError(AIError):
    code, status_code = "AI_AUTHENTICATION_ERROR", 502


class AIRateLimitError(AIError):
    code, status_code = "AI_RATE_LIMIT_ERROR", 429


class AITimeoutError(AIError):
    code, status_code = "AI_TIMEOUT_ERROR", 504


class AIValidationError(AIError):
    code, status_code = "AI_VALIDATION_ERROR", 422


class AIToolError(AIError):
    code, status_code = "AI_TOOL_ERROR", 502


class AIProvider(Protocol):
    name: str

    def generate_with_tools(self, messages: list[dict], tools: list[dict]) -> dict: ...
    def generate_structured(self, messages: list[dict], schema_name: str, schema: dict) -> dict: ...


class GroqProvider:
    """Only this class performs an outbound call to Groq.

    It deliberately returns the raw, provider-normalized message so the agent,
    not the API route, owns validation and tool execution.
    """
    name = "groq"

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        if settings.AI_PROVIDER != "groq" or not settings.GROQ_API_KEY:
            raise AIConfigurationError("Groq is not configured. Set AI_PROVIDER=groq and GROQ_API_KEY.")
        self.base_url = settings.GROQ_BASE_URL.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
        self.transport = transport

    def generate_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        return self._request({
            "model": settings.GROQ_MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": settings.AI_MAX_TOKENS,
            "temperature": 0.1,
        })

    def generate_structured(self, messages: list[dict], schema_name: str, schema: dict) -> dict:
        return self._request({
            "model": settings.GROQ_MODEL, "messages": messages,
            "max_tokens": settings.AI_MAX_TOKENS, "temperature": 0.1,
            # qwen/qwen3.8-27b was live-verified for Groq's json_object mode.
            # Pydantic validates the object before it enters the response.
            "response_format": {"type": "json_object"},
        })

    def _request(self, payload: dict[str, Any]) -> dict:
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=settings.AI_TIMEOUT_SECONDS, transport=self.transport) as client:
                response = client.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload)
        except httpx.TimeoutException as exc:
            raise AITimeoutError("Groq request timed out") from exc
        except httpx.HTTPError as exc:
            raise AIError("Groq request failed") from exc
        if response.status_code in (401, 403):
            raise AIAuthenticationError("Groq authentication failed")
        if response.status_code == 429:
            raise AIRateLimitError("Groq is rate limiting requests")
        if response.status_code >= 400:
            raise AIError(f"Groq returned HTTP {response.status_code}")
        try:
            body = response.json()
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIValidationError("Groq returned an invalid completion") from exc
        return {"message": message, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "model": settings.GROQ_MODEL}
