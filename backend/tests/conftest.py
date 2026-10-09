"""Shared pytest fixtures.

Disables the in-process rate limiter for tests: the limiter is an
infrastructure guard, not the behaviour under test, and its process-local
window is shared across every test in a session (which would make ordering
dependant 429s).
"""
from __future__ import annotations

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _disable_rate_limiter(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    yield
