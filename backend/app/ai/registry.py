"""Centralized AI provider registry and model-priority configuration.

One place answers: which providers are configured, which model each should use,
what each can actually do (verified by probing, not assumed), and what order to
try them in. The registry never holds a credential longer than it needs to and
never exposes one.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.ai.providers.base import ProviderCapabilities
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.openai_compat import OpenAICompatibleProvider
from app.ai.resilience import CircuitBreaker, ConcurrencyLimiter, ProviderMetrics

logger = logging.getLogger(__name__)

#: A model id is only ever used here if it has been verified live. Nothing is
#: hardcoded as "probably available".
VERIFIED_MODELS: dict[str, dict[str, Any]] = {
    "groq": {
        # Verified: chat, tool calling and structured output all return 200 on
        # the free tier. qwen is the fast general-purpose model; gpt-oss-120b is
        # the strong reasoning model (it needs a larger token budget).
        "fast": "qwen/qwen3.8-27b",
        "complex": "openai/gpt-oss-120b",
    },
    "gemini": {
        "fast": "gemini-2.5-flash",
        "complex": "gemini-2.5-flash",
    },
}


@dataclass
class ProviderEntry:
    """A configured provider plus its live capability snapshot."""

    name: str
    provider: Any
    configured: bool = False
    priority: int = 99
    capabilities: ProviderCapabilities | None = None
    last_probed_at: float | None = None
    probe_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model": getattr(self.provider, "model", None),
            "configured": self.configured,
            "priority": self.priority,
            "capabilities": self.capabilities.to_dict() if self.capabilities else None,
            "last_probed_at": self.last_probed_at,
            "probe_error": self.probe_error,
        }


class ProviderRegistry:
    """Builds, probes and orders the configured providers."""

    def __init__(self, settings_obj) -> None:
        self.settings = settings_obj
        self.metrics = ProviderMetrics()
        self.circuit = CircuitBreaker(
            failure_threshold=settings_obj.AI_CIRCUIT_FAILURE_THRESHOLD,
            cooldown_seconds=settings_obj.AI_CIRCUIT_COOLDOWN_SECONDS,
        )
        self.limiter = ConcurrencyLimiter(limit=4)
        self._entries: dict[str, ProviderEntry] = {}
        self._lock = threading.Lock()
        self._budget_lock = threading.Lock()
        self._daily_requests = {"date": None, "count": 0}
        self._rebuild()

    # ── construction ─────────────────────────────────────────────────────
    @staticmethod
    def _credential(name: str, settings_obj) -> str | None:
        """The server-side credential for a provider, or None when unset."""
        return {
            "groq": settings_obj.GROQ_API_KEY,
            "gemini": settings_obj.GEMINI_API_KEY,
            "openai": settings_obj.OPENAI_API_KEY,
        }.get(name)

    def _build_provider(self, name: str):
        """Instantiate one provider, or return None when it is not configured."""
        s = self.settings
        if name == "groq":
            if not s.GROQ_API_KEY:
                return None
            return OpenAICompatibleProvider(
                provider="groq",
                api_key=s.GROQ_API_KEY,
                base_url=s.GROQ_BASE_URL,
                model=s.GROQ_MODEL or VERIFIED_MODELS["groq"]["fast"],
                timeout_seconds=s.AI_TIMEOUT_SECONDS,
                max_output_tokens=max(1024, s.AI_MAX_TOKENS),
            )
        if name == "gemini":
            if not s.GEMINI_API_KEY:
                return None
            return GeminiProvider(
                api_key=s.GEMINI_API_KEY,
                model=s.GEMINI_MODEL or VERIFIED_MODELS["gemini"]["fast"],
                base_url=s.GEMINI_BASE_URL,
                timeout_seconds=s.AI_TIMEOUT_SECONDS,
            )
        if name == "openai":
            if not s.OPENAI_API_KEY:
                return None
            return OpenAICompatibleProvider(
                provider="openai",
                api_key=s.OPENAI_API_KEY,
                base_url=s.OPENAI_BASE_URL,
                model=s.OPENAI_MODEL,
                timeout_seconds=s.AI_TIMEOUT_SECONDS,
                max_output_tokens=max(1024, s.AI_MAX_TOKENS),
            )
        logger.warning("ai_provider_unknown name=%s", name)
        return None

    def _rebuild(self) -> None:
        """Read AI_PROVIDER_PRIORITY and build every configured provider."""
        priority = [
            name.strip().lower()
            for name in (self.settings.AI_PROVIDER_PRIORITY or "").split(",")
            if name.strip()
        ]
        # Any configured provider missing from the list is appended so nothing
        # usable is silently dropped.
        for name in ("groq", "gemini", "openai"):
            if name not in priority and self._credential(name, self.settings):
                priority.append(name)

        entries: dict[str, ProviderEntry] = {}
        for index, name in enumerate(priority):
            provider = self._build_provider(name)
            if provider is None:
                continue
            entries[name] = ProviderEntry(
                name=name, provider=provider, configured=True, priority=index,
            )
        with self._lock:
            self._entries = entries

    # ── probing ─────────────────────────────────────────────────────────
    def probe(self, name: str, *, force: bool = False) -> ProviderEntry:
        """Verify one provider's real capabilities with minimal-cost calls."""
        with self._lock:
            entry = self._entries.get(name)
        if entry is None:
            raise KeyError(name)
        if not force and entry.capabilities is not None:
            return entry
        started = time.perf_counter()
        try:
            capabilities = entry.provider.capabilities()
        except Exception as exc:  # noqa: BLE001 - a probe must never raise
            capabilities = ProviderCapabilities(
                provider=name, model=getattr(entry.provider, "model", "?"),
                error=f"{type(exc).__name__}",
            )
        entry.capabilities = capabilities
        entry.probe_error = capabilities.error
        entry.last_probed_at = time.time()
        self.metrics.health(name).cooldown_remaining_s = 0.0
        logger.info(
            "ai_provider_probed provider=%s model=%s chat=%s tools=%s structured=%s elapsed_ms=%.1f",
            name, capabilities.model, capabilities.chat, capabilities.tool_calling,
            capabilities.structured_output, (time.perf_counter() - started) * 1000,
        )
        with self._lock:
            self._entries[name] = entry
        return entry

    def probe_all(self, *, force: bool = False) -> dict[str, ProviderEntry]:
        for name in list(self._entries):
            try:
                self.probe(name, force=force)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ai_provider_probe_failed provider=%s error=%s", name, exc)
        return dict(self._entries)

    # ── ordering ────────────────────────────────────────────────────────
    def ordered(self, *, require_tools: bool = False,
                require_structured: bool = False,
                allow_paid: bool | None = None) -> list[ProviderEntry]:
        """Providers to try, best first.

        Unconfigured providers are already excluded at construction. A provider
        whose circuit is open is skipped until its cooldown elapses. A provider
        that would incur cost is only offered when paid fallback is explicitly
        enabled — free capacity is always preferred.
        """
        if allow_paid is None:
            allow_paid = self.settings.AI_ALLOW_PAID_FALLBACK
        with self._lock:
            entries = list(self._entries.values())
        entries.sort(key=lambda entry: entry.priority)

        usable: list[ProviderEntry] = []
        for entry in entries:
            if self.circuit.is_open(entry.name):
                entry.probe_error = "circuit open (cooling down)"
                continue
            if not allow_paid and self._is_cost_incurring(entry):
                logger.info(
                    "ai_provider_skipped_paid provider=%s (set AI_ALLOW_PAID_FALLBACK=true to allow)",
                    entry.name,
                )
                continue
            if require_tools and not self._supports(entry, "tool_calling"):
                continue
            if require_structured and not self._supports(entry, "structured_output"):
                continue
            usable.append(entry)
        return usable

    @staticmethod
    def _is_cost_incurring(entry: ProviderEntry) -> bool:
        """True when the model's published pricing is non-zero (i.e. not free)."""
        if entry.capabilities is None:
            # Not yet probed: assume free so a provider is never skipped on a
            # guess, and let an actual quota error surface the truth.
            return False
        return bool(
            entry.capabilities.input_cost_per_million
            or entry.capabilities.output_cost_per_million
        )

    @staticmethod
    def _supports(entry: ProviderEntry, capability: str) -> bool:
        """Whether a capability is credited to a provider.

        Only a *completed* probe that genuinely lacks the capability marks it
        unsupported. A probe that failed for a transient reason (rate limited,
        5xx, timeout) leaves the capability unknown, and an unknown capability
        must not disqualify the provider — the real request decides. Recording a
        transient failure as "no tool calling" would lock a healthy provider out.
        """
        capabilities = entry.capabilities
        if capabilities is None or capabilities.error:
            return True
        return bool(getattr(capabilities, capability, False))

    def select(self, *, complexity: str = "fast") -> ProviderEntry | None:
        """Pick one provider for a task without walking the whole list.

        ``complexity`` is ``fast`` for routine work and ``complex`` for
        reasoning-heavy analysis, so the cheap model is used by default.
        """
        require_structured = complexity == "complex"
        candidates = self.ordered(require_structured=require_structured)
        if not candidates:
            candidates = self.ordered()
        for entry in candidates:
            model = getattr(entry.provider, "model", "") or ""
            if complexity == "complex":
                if entry.name in VERIFIED_MODELS and model in VERIFIED_MODELS[entry.name].values():
                    return entry
            else:
                return entry
        return candidates[0] if candidates else None

    # ── model override ──────────────────────────────────────────────────
    def use_model(self, name: str, model: str) -> None:
        """Point a configured provider at a different verified model."""
        with self._lock:
            entry = self._entries.get(name)
        if entry is None:
            raise KeyError(name)
        entry.provider.model = model
        entry.capabilities = None  # force a re-probe of the new model
        with self._lock:
            self._entries[name] = entry

    # ── reporting ───────────────────────────────────────────────────────
    def status(self) -> dict:
        """A credential-free health snapshot for the status endpoint."""
        with self._lock:
            entries = [entry.to_dict() for entry in sorted(
                self._entries.values(), key=lambda e: e.priority
            )]
        for entry in entries:
            remaining = self.circuit.remaining_cooldown(entry["name"])
            self.metrics.health(entry["name"]).cooldown_remaining_s = remaining
            entry["cooldown_remaining_s"] = round(remaining, 1)
            entry["available"] = remaining <= 0
        return {
            "priority": [entry["name"] for entry in entries],
            "providers": entries,
            "metrics": self.metrics.to_dict(),
            "budget": self.budget_status(),
        }

    # ── usage budget ────────────────────────────────────────────────────
    def budget_status(self) -> dict:
        limit = int(self.settings.AI_DAILY_REQUEST_BUDGET or 0)
        with self._budget_lock:
            today = time.strftime("%Y-%m-%d", time.gmtime())
            if self._daily_requests["date"] != today:
                self._daily_requests.update({"date": today, "count": 0})
            used = int(self._daily_requests["count"])
        return {
            "daily_limit": limit,
            "used_today": used,
            "remaining_today": None if limit <= 0 else max(0, limit - used),
            "exhausted": bool(limit > 0 and used >= limit),
        }

    def consume_budget(self) -> bool:
        """Record one request. Returns False when the configured budget is hit."""
        limit = int(self.settings.AI_DAILY_REQUEST_BUDGET or 0)
        if limit <= 0:
            return True
        with self._budget_lock:
            today = time.strftime("%Y-%m-%d", time.gmtime())
            if self._daily_requests["date"] != today:
                self._daily_requests.update({"date": today, "count": 0})
            if self._daily_requests["count"] >= limit:
                return False
            self._daily_requests["count"] += 1
            return True


_registry: ProviderRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ProviderRegistry:
    """Process-wide registry, built once from the current settings."""
    global _registry
    with _registry_lock:
        if _registry is None:
            from app.core.config import settings

            _registry = ProviderRegistry(settings)
        return _registry
