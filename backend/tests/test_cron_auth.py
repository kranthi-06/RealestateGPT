"""Tests for the server-only Vercel Cron authorization boundary."""
from __future__ import annotations

from app.api.v1.workers import CRON_JOBS, WORKER_FUNCTIONS, _verify_cron_secret
from app.core.config import settings


def test_cron_jobs_reference_registered_workers():
    assert CRON_JOBS
    assert all(worker in WORKER_FUNCTIONS for workers in CRON_JOBS.values() for worker in workers)


def test_cron_authorization_requires_exact_bearer_secret(monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", "cron-secret-long-enough")

    assert _verify_cron_secret("Bearer cron-secret-long-enough") is True
    assert _verify_cron_secret("Bearer wrong-secret") is False
    assert _verify_cron_secret("Basic cron-secret-long-enough") is False
    assert _verify_cron_secret(None) is False


def test_cron_authorization_fails_closed_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", None)
    assert _verify_cron_secret("Bearer any-value") is False
