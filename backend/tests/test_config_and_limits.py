"""Unit tests for production configuration validation and rate limiting."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.rate_limit import RateLimiter


def test_development_configuration_allows_placeholder_secrets():
    settings = Settings(
        APP_ENV="development",
        MONGODB_URI="",
        SECRET_KEY="change-this-in-production",
        AI_PROVIDER="offline",
    )
    problems = settings.validate_runtime()
    # MONGODB_URI is always required; placeholder secret may stay only in dev.
    assert any("MONGODB_URI" in p for p in problems)
    assert not any("SECRET_KEY" in p for p in problems)


def test_production_configuration_rejects_weak_secrets():
    settings = Settings(
        APP_ENV="production",
        MONGODB_URI="mongodb+srv://user:pass@cluster.example.mongodb.net",
        SECRET_KEY="change-this-in-production",
        AI_PROVIDER="groq",
        GROQ_API_KEY="k",
        LOCATION_PROVIDER="osm",
    )
    problems = settings.validate_runtime()
    assert any("SECRET_KEY" in p for p in problems)


def test_production_configuration_requires_groq():
    settings = Settings(
        APP_ENV="production",
        MONGODB_URI="mongodb+srv://user:pass@cluster.example.mongodb.net",
        SECRET_KEY="a-very-long-random-secret-key-value-0123456789",
        AI_PROVIDER="offline",
        LOCATION_PROVIDER="osm",
    )
    problems = settings.validate_runtime()
    assert any("GROQ_API_KEY" in p for p in problems)


def test_production_configuration_requires_cron_secret():
    settings = Settings(
        APP_ENV="production",
        MONGODB_URI="mongodb+srv://user:pass@cluster.example.mongodb.net",
        SECRET_KEY="a-very-long-random-secret-key-value-0123456789",
        AI_PROVIDER="groq",
        GROQ_API_KEY="k",
        LOCATION_PROVIDER="osm",
    )
    problems = settings.validate_runtime()
    assert any("CRON_SECRET" in p for p in problems)


def test_rate_limiter_enforces_sliding_window():
    limiter = RateLimiter()
    for _ in range(3):
        limiter.check("ip:test", limit=3, window_seconds=60, enabled=True)
    with pytest.raises(Exception):
        limiter.check("ip:test", limit=3, window_seconds=60, enabled=True)


def test_rate_limiter_can_be_disabled():
    limiter = RateLimiter()
    for _ in range(20):
        limiter.check("ip:test", limit=3, window_seconds=60, enabled=False)  # no exception
