"""Property data providers.

Only legitimate/authorized sources are adapted. When no provider is configured,
``get_property_provider()`` returns a sentinel that raises
``ProviderNotConfiguredError`` — the system never fabricates inventory.
"""
from app.providers.property.errors import (
    ProviderError,
    ProviderListingNotFoundError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.property.registry import (
    get_property_provider,
    provider_configuration_error,
    registered_names,
)

__all__ = [
    "ProviderError",
    "ProviderListingNotFoundError",
    "ProviderNotConfiguredError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "get_property_provider",
    "provider_configuration_error",
    "registered_names",
]