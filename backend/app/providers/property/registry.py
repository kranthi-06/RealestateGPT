"""Property adapter registry and configuration-driven selection."""
from __future__ import annotations

import logging
from typing import Dict, Type

from app.core.config import settings
from app.providers.property.adapters.base import BasePropertyAdapter
from app.providers.property.errors import ProviderNotConfiguredError

logger = logging.getLogger(__name__)

#: name -> adapter class. New licensed adapters register here.
REGISTRY: Dict[str, Type[BasePropertyAdapter]] = {}


def register(name: str, adapter_cls: Type[BasePropertyAdapter]) -> None:
    REGISTRY[name] = adapter_cls


def registered_names() -> list[str]:
    return sorted(REGISTRY)


def get_property_provider() -> BasePropertyAdapter:
    """Return the adapter selected by PROPERTY_PROVIDER, or a sentinel that
    explains inventory is intentionally empty.

    ``property_ingestion`` imports this module (via the package ``__init__``)
    so the registration side effect below always runs.
    """
    from app.providers.property.unconfigured import UnconfiguredPropertyProvider

    name = (settings.PROPERTY_PROVIDER or "").strip().lower()
    if not name:
        return UnconfiguredPropertyProvider()
    adapter_cls = REGISTRY.get(name)
    if adapter_cls is None:
        logger.warning(
            "property_provider_not_registered name=%s available=%s",
            name, ",".join(registered_names()) or "none",
        )
        return UnconfiguredPropertyProvider()
    try:
        return adapter_cls()
    except ProviderNotConfiguredError:  # e.g. missing credential/config file
        logger.warning("property_provider_config_error name=%s", name)
        return UnconfiguredPropertyProvider()


def provider_configuration_error() -> str:
    """Human-readable reason production inventory is unavailable."""
    name = (settings.PROPERTY_PROVIDER or "").strip().lower()
    if not name:
        return "No property provider is configured. Set PROPERTY_PROVIDER to ingest real listings."
    if name not in REGISTRY:
        return f"Property provider '{name}' is not registered. Registered: {', '.join(registered_names()) or 'none'}."
    return f"Property provider '{name}' is selected but could not be initialized. Check its configuration."


def import_admin_import_provider() -> None:
    """Register the admin-import adapter (idempotent)."""
    from app.providers.property.adapters.admin_import import AdminImportProvider

    if "admin_import" not in REGISTRY:
        register("admin_import", AdminImportProvider)


import_admin_import_provider()