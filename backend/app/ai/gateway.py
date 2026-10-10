"""Central AI gateway: provider fallback, retries, circuit breaking, budgets.

This is the ONLY place that talks to an AI provider. Callers ask for a
completion; the gateway picks the best available provider, retries transient
failures on the same provider, then falls through to the next one. When every
provider fails it raises a typed ``AIError`` — it never fabricates a response.

Grounding rule enforced here and nowhere else: this gateway only ever returns
what a provider produced. Property data always comes from MongoDB through the
tool registry, so a fallback model cannot invent a listing, a price or a
financial figure.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.ai.providers.base import ChatResult
from app.ai.registry import VERIFIED_MODELS, ProviderRegistry, get_registry
from app.ai.resilience import (
    RetryPolicy,
    backoff_delay,
    is_permanent_status,
    is_retryable_status,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Error hierarchy (unchanged public contract) ──────────────────────────

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

    def __init__(self, message: str, *, cause: Exception | None = None, retry_after: float | None = None) -> None:
        super().__init__(message, cause=cause)
        self.retry_after = retry_after


class AITimeoutError(AIError):
    code, status_code = "AI_TIMEOUT_ERROR", 504


class AIValidationError(AIError):
    code, status_code = "AI_VALIDATION_ERROR", 422


class AIToolError(AIError):
    code, status_code = "AI_TOOL_ERROR", 502


class AIUnavailableError(AIError):
    """Every configured provider failed."""

    code, status_code = "AI_ALL_PROVIDERS_UNAVAILABLE", 503


# ── Compatibility names kept for existing imports ────────────────────────

AIAuthenticationError_ = AIAuthenticationError  # noqa: N816  (documented alias)


class AIProvider:
    """Backwards-compatible single-provider view over the registry.

    Existing code constructed ``GroqProvider()``; the gateway now resolves the
    primary provider through the registry so fallback works transparently.
    """

    name = "auto"

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self._registry = registry or get_registry()


GroqProvider = AIProvider  # legacy import name


# ── The gateway ──────────────────────────────────────────────────────────

class AIGateway:
    """Routes a completion through the configured providers with fallback."""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self._registry = registry or get_registry()
        s = settings
        self.retry = RetryPolicy(
            max_attempts=max(1, s.AI_MAX_ATTEMPTS),
            base_seconds=s.AI_RETRY_BASE_SECONDS,
            max_seconds=s.AI_RETRY_MAX_SECONDS,
        )

    # ── public API ───────────────────────────────────────────────────────
    def chat(self, messages: list[dict], tools: list[dict], *,
             max_tokens: int | None = None, structured: bool = False,
             complexity: str = "fast") -> ChatResult:
        """Produce one completion, trying providers in priority order.

        ``complexity`` selects the model tier: ``fast`` for routine work,
        ``complex`` for reasoning-heavy analysis. Either way the same fallback
        chain applies, so a simple query still works when the fast model is
        unavailable.
        """
        if not self._registry.consume_budget():
            raise AIRateLimitError("The configured daily AI request budget is exhausted.")

        token_budget = max_tokens or settings.AI_MAX_TOKENS
        # A reasoning tier needs a bigger output budget: Groq's strong model
        # spends tokens on internal reasoning before it emits anything.
        if complexity == "complex":
            token_budget = max(token_budget, 2000)
        require_tools = bool(tools)
        candidates = self._registry.ordered(
            require_tools=require_tools, require_structured=structured,
        )
        if not candidates:
            # Nothing configured at all is a deployment problem; providers that
            # exist but are all cooling down is a transient availability problem.
            configured = list(getattr(self._registry, "_entries", {}))
            if not configured:
                raise AIConfigurationError(
                    "No AI provider is configured. Set a provider API key "
                    "in the backend environment."
                )
            raise AIUnavailableError(
                "Every configured AI provider is unavailable right now "
                f"({', '.join(configured)}). Please try again shortly."
            )

        # Capability-aware model tier: for reasoning-heavy work, prefer the
        # verified strong model on each provider when it is available in this
        # candidate set. Falls through to the normal order otherwise.
        tier_model = self._tier_model(complexity)
        if complexity == "complex" and tier_model:
            candidates = self._prefer_model(candidates, tier_model)

        attempts: list[str] = []
        last_error: Exception | None = None
        for entry in candidates:
            name = entry.name
            attempts.append(name)
            try:
                return self._call_with_retry(
                    entry, messages, tools, token_budget, structured, tier_model,
                )
            except Exception as exc:  # noqa: BLE001 - classify then fall through
                last_error = exc
                classified = self._classify(exc)
                if classified is not None:
                    # Permanent: no point trying the same thing elsewhere.
                    logger.warning(
                        "ai_provider_permanent_error provider=%s code=%s",
                        name, classified.code,
                    )
                    self._registry.metrics.health(name).record(
                        success=False, latency_ms=0.0, error=classified.code)
                    self._registry.circuit.record_failure(name)
                    raise classified
                logger.warning(
                    "ai_provider_failed_falling_back provider=%s next=%s error=%s",
                    name, attempts[-1] if len(attempts) > 1 else "none", type(exc).__name__,
                )
                self._registry.metrics.health(name).record(
                    success=False, latency_ms=0.0, error=type(exc).__name__)

        detail = f"providers tried: {', '.join(attempts)}"
        raise AIUnavailableError(
            f"All AI providers are unavailable right now. {detail}. "
            "Please try again shortly."
        ) from last_error

    def generate_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        """OpenAI-shaped completion with tools, for the existing agent loop."""
        result = self.chat(messages, tools, complexity="fast")
        return {
            "message": {
                "role": "assistant",
                "content": result.message.content,
                "tool_calls": result.message.tool_calls,
            },
            "latency_ms": result.latency_ms,
            "model": result.model,
            "provider": result.provider,
        }

    def generate_structured(self, messages: list[dict], schema_name: str, schema: dict) -> dict:
        """JSON-mode completion, for the structured final answer."""
        result = self.chat(messages, [], structured=True, complexity="fast")
        return {
            "message": {"role": "assistant", "content": result.message.content},
            "latency_ms": result.latency_ms,
            "model": result.model,
            "provider": result.provider,
        }

    # ── internals ────────────────────────────────────────────────────────
    def _call_with_retry(self, entry, messages: list[dict], tools: list[dict],
                         max_tokens: int, structured: bool,
                         model: str | None = None) -> ChatResult:
        """Bounded retries on ONE provider, then give up on it."""
        name = entry.name
        delays = self.retry.delays()
        last_exc: Exception | None = None
        for attempt in range(self.retry.max_attempts):
            started = time.perf_counter()
            try:
                with self._registry.limiter.slot():
                    result = entry.provider.chat(
                        messages, tools, max_tokens=max_tokens, structured=structured,
                        model=model,
                    )
            except Exception as exc:  # noqa: BLE001
                status = _status_of(exc)
                health = self._registry.metrics.health(name)
                health.record(success=False, latency_ms=(time.perf_counter() - started) * 1000,
                              error=_status_of(exc) or type(exc).__name__)
                if status == 429:
                    health.rate_limited += 1
                elif _is_timeout(exc):
                    health.timeouts += 1
                if is_permanent_status(status):
                    raise
                if status is not None and not is_retryable_status(status):
                    raise
                last_exc = exc
                if attempt < len(delays):
                    delay = delays[attempt]
                    logger.info(
                        "ai_retry provider=%s attempt=%s delay_s=%.2f status=%s",
                        name, attempt + 1, delay, status,
                    )
                    time.sleep(delay)
                continue

            health = self._registry.metrics.health(name)
            health.record(success=True, latency_ms=result.latency_ms,
                          tokens=result.total_tokens, cost_usd=result.estimated_cost_usd)
            self._registry.circuit.record_success(name)
            if attempt > 0:
                logger.info("ai_retry_recovered provider=%s attempts=%s", name, attempt + 1)
            return result

        self._registry.circuit.record_failure(name)
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _tier_model(complexity: str) -> str | None:
        """The verified model id for a tier, or None to use each default."""
        if complexity != "complex":
            return None
        return VERIFIED_MODELS["groq"]["complex"]

    @staticmethod
    def _prefer_model(candidates: list, model: str) -> list:
        """Move a provider to the front when it can serve ``model``.

        Only reorders providers that are already eligible; never adds one.
        """
        preferred = None
        for entry in candidates:
            provider_model = getattr(entry.provider, "model", "")
            # A provider can serve the tier model when it is a Groq model (the
            # tier is only defined for Groq) or already configured for it.
            if model == provider_model or (
                entry.name == "groq" and model in VERIFIED_MODELS.get("groq", {}).values()
            ):
                preferred = entry
                break
        if preferred is None:
            return candidates
        reordered = [preferred]
        reordered.extend(entry for entry in candidates if entry is not preferred)
        return reordered

    @staticmethod
    def _classify(exc: Exception) -> AIError | None:
        """Map a provider exception to a typed AIError, or None if retryable.

        Only genuinely permanent conditions (bad credential, malformed request,
        unknown model) are raised immediately: retrying them anywhere wastes
        quota and hides the real problem. Timeouts, rate limits and 5xx are
        transient and must fall through to the next provider.
        """
        status = _status_of(exc)
        if is_permanent_status(status):
            if status in (401, 403):
                return AIAuthenticationError("AI provider rejected the configured credential")
            return AIValidationError("AI provider rejected the request")
        return None


# ── helpers ──────────────────────────────────────────────────────────────

def _status_of(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _is_timeout(exc: BaseException) -> bool:
    import httpx

    return isinstance(exc, (httpx.TimeoutException, TimeoutError))


# ── Module-level convenience ─────────────────────────────────────────────

_gateway: AIGateway | None = None


def get_gateway() -> AIGateway:
    global _gateway
    if _gateway is None:
        _gateway = AIGateway()
    return _gateway
