"""Web search provider package.

External property-web search through configurable, authorized providers
(currently Brave Search API). Providers normalize into
``app.providers.web_search.models`` shapes; adapters never scrape search-engine
result pages and never fabricate results.
"""
from app.providers.web_search.base import BaseWebSearchProvider, WebSearchProvider
from app.providers.web_search.models import (
    WebSearchAuthenticationError,
    WebSearchError,
    WebSearchInternalError,
    WebSearchInvalidRequestError,
    WebSearchNotConfiguredError,
    WebSearchProviderStatus,
    WebSearchRateLimitError,
    WebSearchResponse,
    WebSearchResult,
    WebSearchTimeoutError,
    WebSearchUnavailableError,
)
from app.providers.web_search.registry import (
    get_web_search_provider,
    web_search_health,
)

__all__ = [
    "BaseWebSearchProvider",
    "WebSearchProvider",
    "WebSearchResult",
    "WebSearchResponse",
    "WebSearchProviderStatus",
    "WebSearchError",
    "WebSearchNotConfiguredError",
    "WebSearchUnavailableError",
    "WebSearchRateLimitError",
    "WebSearchAuthenticationError",
    "WebSearchTimeoutError",
    "WebSearchInvalidRequestError",
    "WebSearchInternalError",
    "get_web_search_provider",
    "web_search_health",
]