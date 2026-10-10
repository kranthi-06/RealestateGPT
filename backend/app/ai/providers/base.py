"""Common AI provider interface.

Every provider — Groq, Gemini, OpenAI — speaks a different wire format. Each
adapter translates into the one normalized shape below, so the agent and the
fallback router never need provider-specific code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ChatMessage:
    """One normalized assistant turn.

    ``content`` is the text (may be empty when the model only calls tools) and
    ``tool_calls`` holds the provider-normalized tool invocations.
    """

    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    #: Provider-native extras, kept so debugging never needs the raw response.
    raw: dict = field(default_factory=dict)


@dataclass
class ChatResult:
    """The outcome of one provider call, with the cost/telemetry attached."""

    message: ChatMessage
    model: str
    provider: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass
class ProviderCapabilities:
    """What a model can do, discovered by probing rather than assumed."""

    provider: str
    model: str
    chat: bool = False
    tool_calling: bool = False
    structured_output: bool = False
    #: USD per 1M tokens, used for the cost estimate. 0 for free-tier models.
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0
    #: Rough relative cost tier, used to prefer cheap models for simple work.
    cost_tier: str = "free"  # free | cheap | paid
    max_output_tokens: int = 4096
    latency_ms: float | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "chat": self.chat,
            "tool_calling": self.tool_calling,
            "structured_output": self.structured_output,
            "cost_tier": self.cost_tier,
            "input_cost_per_million": self.input_cost_per_million,
            "output_cost_per_million": self.output_cost_per_million,
            "max_output_tokens": self.max_output_tokens,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class AIProvider(Protocol):
    """The one interface the agent and the fallback router program against."""

    name: str
    model: str

    def chat(self, messages: list[dict], tools: list[dict], *, max_tokens: int,
             structured: bool = False, model: str | None = None) -> ChatResult: ...

    def capabilities(self) -> ProviderCapabilities: ...
