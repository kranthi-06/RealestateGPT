import os

base = "e:/Realestate gpt/backend/app/provider_registry"

init = """\"\"\"
Web search provider registry package.

Entry point for the web search integration: :func:`get_web_search_provider()`
returns a configured adapter, and :class:`WebSearchResult` / :class:`WebSearchResponse`
are the only result shapes the rest of the application sees.
\"\"\"

from __future__ import annotations

from .api import get_web_search_provider
from .models import WebSearchResult, WebSearchResponse

__all__ = ["get_web_search_provider", "WebSearchResult", "WebSearchResponse"]
"""

api = """\"\"\"
Provider registry: resolves a named web search provider to a live adapter.

Central point of truth for the web search integration. Callers obtain a ready-to-
use provider via :func:`get_web_search_provider()`. A missing configuration yields
the typed :class:`WebSearchNotConfiguredError` state - the application NEVER
substitutes fake or demo results.
\"\"\"

from __future__ import annotations

from app.core.config import settings
from app.providers.web_search.base import BaseWebSearchProvider
from app.providers.web_search.models import WebSearchNotConfiguredError


def registered_providers() -> list[str]:
    from app.providers.web_search.registry import registered_providers

    return registered_providers()


def get_web_search_provider() -> BaseWebSearchProvider:
    \"\"\"Return the configured provider adapter (module-level override supported).\"\"\"
    name = (settings.WEB_SEARCH_PROVIDER or "").strip().lower()
    if name == "brave":
        from app.providers.web_search.brave import BraveSearchProvider

        return BraveSearchProvider()
    if name == "searxng":
        from app.providers.web_search.searxng import SearXNGSearchProvider

        return SearXNGSearchProvider()
    if name == "tavily":
        from app.providers.web_search.tavily import TavilySearchProvider

        return TavilySearchProvider()
    if not name:
        raise WebSearchNotConfiguredError("WEB_SEARCH_PROVIDER is not configured.")
    raise WebSearchNotConfiguredError(
        f\"Web search provider '{name}' is not registered. Registered: {', '.join(registered_providers()) or 'none'}."
    )
"""

models = """\"\"\"
Typed errors and status models for the web search provider layer.

Every provider adapter normalizes into :class:`WebSearchResult` / :class:`WebSearchResponse`
and never leaks provider-specific response structures. Missing configuration and
provider failures surface as typed states that callers render honestly.
\"\"\"

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class WebSearchResult(BaseModel):
    \"\"\"
    Normalized web search result consumed by property candidate extraction.

    Only fields that can actually be populated from the provider are set;
    everything else stays ``None``.
    \"\"\"

    id: str
    title: str
    url: str
    domain: str
    description: Optional[str] = None
    source_name: Optional[str] = None
    page_age: Optional[str] = None
    page_fetched: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    language: Optional[str] = None
    is_live: bool = True
    schemas: list[dict[str, Any]] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str = "web"
    retrieved_at: datetime = Field(default_factory=_utcnow)

    @field_validator("url")
    @classmethod
    def _safe_http_url(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) > 2048:
            raise ValueError("url is too long")
        return v
"""

for name, content in [("__init__.py", init), ("api.py", api), ("models.py", models)]:
    path = os.path.join(base, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("WROTE", path, len(content))
