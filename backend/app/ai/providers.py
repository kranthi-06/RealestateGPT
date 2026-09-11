"""Compatibility exports for the configured real AI provider.

There is intentionally no offline/fake assistant provider. Missing Groq
configuration is a controlled configuration error.
"""
from app.ai.gateway import AIProvider, GroqProvider


def get_provider() -> AIProvider:
    return GroqProvider()
