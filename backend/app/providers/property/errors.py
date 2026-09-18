"""Typed provider errors so callers never confuse absence of inventory with
provider or network failure."""


class ProviderError(RuntimeError):
    code = "PROVIDER_ERROR"


class ProviderNotConfiguredError(ProviderError):
    """No provider is configured in the environment. Inventory is intentionally
    empty rather than fabricated."""

    code = "PROVIDER_NOT_CONFIGURED"


class ProviderUnavailableError(ProviderError):
    """The configured provider cannot currently be reached (network, outage)."""

    code = "PROVIDER_UNAVAILABLE"


class ProviderRateLimitError(ProviderError):
    """The provider asked the client to slow down."""

    code = "PROVIDER_RATE_LIMIT"


class ProviderTimeoutError(ProviderError):
    """The provider did not answer within the configured timeout."""

    code = "PROVIDER_TIMEOUT"


class ProviderListingNotFoundError(ProviderError):
    """The provider confirmed a listing no longer exists / is no longer live.

    This is the ONLY signal that may move an active listing to an inactive
    state. Provider/network failures raise ProviderUnavailableError instead."""

    code = "PROVIDER_LISTING_NOT_FOUND"