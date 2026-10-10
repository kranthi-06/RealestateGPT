"""Provider registry package.

Exposes the adapters behind the common interface, so callers never import a
provider-specific module directly.
"""
from app.ai.providers.base import (  # noqa: F401
    ChatMessage,
    ChatResult,
    ProviderCapabilities,
)
from app.ai.providers.gemini import GeminiProvider  # noqa: F401
from app.ai.providers.openai_compat import OpenAICompatibleProvider  # noqa: F401
