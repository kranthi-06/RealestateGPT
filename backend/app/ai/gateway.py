"""Small, provider-isolated Groq OpenAI-compatible gateway."""
from __future__ import annotations

import logging
import time
from typing import Any, Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIError(RuntimeError):
    """Provider-level error that preserves the underlying cause without leaking internals."""

    code = "AI_PROVIDER_ERROR"
    status_code = 502

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self._cause = cause

    @property
    def message(self) -> str:
        return str(self)


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
        attempts = 0
        while True:
            attempts += 1
            try:
                with httpx.Client(timeout=settings.AI_TIMEOUT_SECONDS, transport=self.transport) as client:
                    response = client.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload)
            except httpx.TimeoutException as exc:
                raise AITimeoutError("Groq request timed out") from exc
            except httpx.HTTPError as exc:
                raise AIError(f"Groq request failed: {exc}", cause=exc) from exc
            if response.status_code in (401, 403):
                raise AIAuthenticationError("Groq authentication failed")
            if response.status_code == 429:
                # Bounded single retry for the same provider; never a substitute.
                if attempts < 2:
                    logger.warning("groq_rate_limited attempt=%s retrying", attempts)
                    time.sleep(2.0 * attempts)
                    continue
                raise AIRateLimitError("Groq is rate limiting requests")
            if response.status_code >= 400:
                detail = response.text[:500]
                logger.error("groq_http_error status=%s detail=%s", response.status_code, detail)
                raise AIError(f"Groq returned HTTP {response.status_code}", cause=HTTPError(f"HTTP {response.status_code}: {detail}"))
            break
        try:
            body = response.json()
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIValidationError("Groq returned an invalid completion") from exc
        if response.is_json:
            try:
                body = response.json()
                if body.get("error"):
                    err = body["error"]
                    err_type = err.get("type", "unknown") if isinstance(err, dict) else "unknown"
                    err_msg = err.get("message", response.text[:500]) if isinstance(err, dict) else response.text[:500]
                    if err_type in {"rate_limit_error", "too_many_requests"}:
                        raise AIRateLimitError(err_msg, retry_after=1.0)
                    raise AIError(err_msg, cause=ValueError(err_msg))
            except (ValueError, TypeError):
                pass
        return {"message": message, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "model": settings.GROQ_MODEL}
