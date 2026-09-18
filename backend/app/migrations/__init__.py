"""Database migrations for RealEstateGPT.

Migrations are idempotent: each applies once (tracked in ``schema_migrations``,)
and each function is safe to re-run against already-migrated data. Run at
startup after indexes are ensured.
"""
from app.migrations.schema_v2 import run_migrations

__all__ = ["run_migrations"]