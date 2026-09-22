"""Web search provider abstraction.

All provider adapters derive from :class:`BaseWebSearchProvider` and must return
the normalized :class:`WebSearchResponse` shape (see ``models.py``). Adapters
never leak provider-specific response structures and never fabricate results.
"""
from __future__ import annotations

import abc
from typing import Optional, Protocol, runtime_checkable

from app.providers.web_search.models import (
    WebSearchProviderStatus,
    WebSearchResponse,
)


@runtime_checkable
class WebSearchProvider(Protocol):
    """Structural contract implemented by every web search provider adapter."""

    name: str

    def search(
        self,
        query: str,
        country: Optional[str] = None,
        language: Optional[str] = None,
        count: int = 20,
        offset: int = 0,
        freshness: Optional[str] = None,
    ) -> WebSearchResponse: ...

    def health(self) -> WebSearchProviderStatus: ...


class BaseWebSearchProvider(abc.ABC):
    """Shared infrastructure (identity + health) for web search adapters."""

    name: str = "web"

    def __init__(self) -> None:
        self._status = WebSearchProviderStatus(provider=self.name)

    @abc.abstractmethod
    def search(
        self,
        query: str,
        country: Optional[str] = None,
        language: Optional[str] = None,
        count: int = 20,
        offset: int = 0,
        freshness: Optional[str] = None,
    ) -> WebSearchResponse:
        """Execute one bounded provider request and return normalized results."""

    def health(self) -> WebSearchProviderStatus:
        """Return the current provider health snapshot (never throws)."""
        return self._status