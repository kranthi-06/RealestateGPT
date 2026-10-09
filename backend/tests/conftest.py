"""Shared pytest fixtures.

Disables the in-process rate limiter for tests: the limiter is an
infrastructure guard, not the behaviour under test, and its process-local
window is shared across every test in a session (which would make ordering
dependent 429s).

It also installs a hard guard so a test run can never mutate a live database.
Several repository/worker tests call ``delete_many({})`` to reset collections;
pointed at a shared cluster those wipe real data. Whenever the configured
MongoDB database is not an obvious *test* database:

* any test that takes a database-touching fixture is skipped, and
* any database access that slips through raises instead of connecting, so
  nothing can be silently written to a live cluster.

Set ``ALLOW_LIVE_DB_TESTS=1`` to override (only ever do that against a
database you own, ideally a local ``*_test`` one).
"""
from __future__ import annotations

import os
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _disable_rate_limiter(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    yield


def _configured_database_name() -> str:
    uri = settings.MONGODB_URI or ""
    try:
        name = urlparse(uri).path.strip("/")
        if name:
            return name.split("?")[0]
    except ValueError:
        pass
    return settings.MONGODB_DATABASE or ""


def _looks_like_test_database(name: str) -> bool:
    lowered = (name or "").lower()
    return lowered in {"test", "testing"} or lowered.endswith(("_test", "-test"))


_DB_NAME = _configured_database_name()
_LIVE_DB_GUARD = not _looks_like_test_database(_DB_NAME) and os.getenv(
    "ALLOW_LIVE_DB_TESTS", ""
).strip().lower() not in {"1", "true", "yes"}

# Fixtures that reach the database (directly, or through the ASGI app).
_DB_FIXTURES = {"mongo", "test_db", "db", "discovery_db", "repository", "client"}

if _LIVE_DB_GUARD:
    # Runs at import time, before any test module binds the database helpers.
    # A plain exception (not pytest's skip outcome) is used so it cannot be
    # swallowed by the ASGI stack: the loud failure names the real problem.
    _guard_message = (
        f"Refusing to touch the live MongoDB database '{_DB_NAME}'. "
        "Point MONGODB_URI/MONGODB_DATABASE at a '*_test' database, or set "
        "ALLOW_LIVE_DB_TESTS=1 if you really mean to run these tests."
    )

    class _LiveDatabaseGuard(RuntimeError):
        pass

    class _GuardedDatabase:
        """Stand-in database handle: every access refuses loudly."""

        def __getitem__(self, _name):
            raise _LiveDatabaseGuard(_guard_message)

        def __getattr__(self, _name):
            raise _LiveDatabaseGuard(_guard_message)

        def __bool__(self):
            raise _LiveDatabaseGuard(_guard_message)

    # Data access is refused outright ...
    patch("app.core.database._get_client", side_effect=_LiveDatabaseGuard(_guard_message)).start()
    # ... and every database handle handed out during a test raises on use, so
    # no route, repository or lifespan hook can silently reach a live cluster.
    patch("app.core.database.get_database", lambda: _GuardedDatabase()).start()
    # Startup bookkeeping is a no-op instead of a failure, so the ASGI app can
    # still be constructed and fixtures that override the database with an
    # in-memory fake behave exactly as they would in CI.
    patch("app.core.database.connect", lambda: None).start()
    patch("app.core.database.ensure_indexes", lambda: None).start()
    patch("app.migrations.run_migrations", lambda *_a, **_kw: None).start()


def pytest_collection_modifyitems(config, items):
    """Skip database-backed tests while a live database is configured."""
    if not _LIVE_DB_GUARD:
        return
    skip_marker = pytest.mark.skip(
        reason=(
            f"Database tests are disabled: the configured MongoDB database "
            f"'{_DB_NAME}' is not a test database."
        )
    )
    for item in items:
        if _DB_FIXTURES.intersection(item.fixturenames):
            item.add_marker(skip_marker)
