"""Provider access for the application.

Production resolves providers through ``app.ai.registry.get_registry`` so the
priority order, capability probing and fallback all live in one place. There is
intentionally no offline/fake assistant provider: a missing credential is a
controlled configuration error, never a silent stub.
"""
from __future__ import annotations

from app.ai.gateway import AIProvider, AIGateway, get_gateway  # noqa: F401
from app.ai.registry import ProviderRegistry, get_registry  # noqa: F401


def get_provider() -> AIGateway:
    """The gateway, i.e. the primary provider with its fallbacks."""
    return get_gateway()
