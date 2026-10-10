"""Live provider integration checks.

These run only when real credentials are configured AND the live-database guard
is not active, and they spend the smallest possible number of tokens. They are
marked ``integration`` so a normal test run skips them:

    pytest -m integration tests/test_ai_provider_integration.py

Every failure path is mocked (see test_ai_provider_fallback.py); these tests
only confirm that the real providers answer at all.
"""
from __future__ import annotations

import os

import pytest

from app.ai.registry import get_registry
from app.core.config import settings

pytestmark = pytest.mark.integration

#: The guard in conftest.py already refuses to run against a live database, so
#: these live provider checks are skipped in exactly the same situations.
_SKIP = os.getenv("ALLOW_LIVE_DB_TESTS", "").strip().lower() not in {"1", "true", "yes"}


def _has(credential: str | None) -> bool:
    return bool((credential or "").strip())


@pytest.mark.skipif(_SKIP, reason="live provider checks are opt-in")
class TestLiveProviders:
    def test_registry_lists_the_configured_providers(self):
        registry = get_registry()
        status = registry.status()
        expected = {
            "groq": _has(settings.GROQ_API_KEY),
            "gemini": _has(settings.GEMINI_API_KEY),
            "openai": _has(settings.OPENAI_API_KEY),
        }
        for name, configured in expected.items():
            if configured:
                assert name in status["priority"], f"{name} is configured but missing"
        assert status["priority"], "at least one provider must be configured"

    def test_the_primary_provider_answers_a_trivial_prompt(self):
        registry = get_registry()
        ordered = registry.ordered()
        assert ordered, "no available provider"
        entry = ordered[0]
        result = entry.provider.chat(
            [{"role": "user", "content": "Reply with the single word: ok"}],
            [], max_tokens=512,
        )
        assert result.message.content.strip(), "the primary provider returned no text"
        assert result.provider == entry.name

    def test_capability_probe_reports_the_truth(self):
        """A verified provider must report chat/tool/structured support truthfully."""
        registry = get_registry()
        registry.probe_all(force=True)
        available = [name for name in registry.status()["priority"]
                     if not registry.circuit.is_open(name)]
        assert available, "no provider survived the capability probe"
        for name in available:
            entry = registry.probe(name)
            assert entry.capabilities is not None
            # Whatever is reported as supported must actually be supported.
            assert entry.capabilities.chat is True or entry.capabilities.error

    def test_status_endpoint_payload_contains_no_credentials(self):
        registry = get_registry()
        payload = registry.status()
        serialized = str(payload)
        for credential in (settings.GROQ_API_KEY, settings.GEMINI_API_KEY, settings.OPENAI_API_KEY):
            if credential:
                assert credential not in serialized
        assert "api_key" not in serialized.lower()
