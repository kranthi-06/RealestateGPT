"""Gemini adapter.

Gemini's ``generateContent`` API is NOT OpenAI-compatible: it takes ``contents``
with ``parts``, declares tools as ``functionDeclarations``, and returns
``functionCall`` parts. This adapter translates in both directions so the rest
of the system sees one normalized shape.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.ai.providers.base import ChatMessage, ChatResult, ProviderCapabilities

logger = logging.getLogger(__name__)

USER_AGENT = "RealEstateGPT/1.0 (+https://realestate-gpt-inky.vercel.app)"

#: Enough tokens for a thinking model to reason AND answer; a tiny budget
#: makes a healthy model look broken (finishReason=MAX_TOKENS, empty text).
PROBE_MAX_TOKENS = 512

#: Gemini's free tier does not bill per token for the models used here.
GEMINI_PRICING = {"input": 0.0, "output": 0.0}


def to_gemini_contents(messages: list[dict]) -> tuple[list[dict], str | None]:
    """Translate OpenAI-style messages into Gemini ``contents``.

    Returns ``(contents, system_instruction)``. Tool results are mapped back to
    ``functionResponse`` parts so a multi-turn tool exchange round-trips.
    """
    system_parts: list[str] = []
    contents: list[dict] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content") or ""

        if role == "system":
            if content:
                system_parts.append(content)
            continue

        if role == "tool":
            # A tool result belongs to the preceding model turn in Gemini.
            contents.append({
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": message.get("name") or "tool",
                        "response": {"result": content},
                    }
                }],
            })
            continue

        if role == "assistant":
            parts: list[dict] = []
            if content:
                parts.append({"text": content})
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                signature = function.get("thought_signature")
                if signature:
                    # Gemini 3.x requires the original thought signature, echoed
                    # back on the Part (a sibling of functionCall).
                    parts.append({
                        "functionCall": {
                            "name": function.get("name") or "tool",
                            "args": _parse_args(function.get("arguments")),
                        },
                        "thoughtSignature": signature,
                    })
                else:
                    # A tool call made by a DIFFERENT provider (the fallback path)
                    # has no Gemini thought signature. Representing it as a formal
                    # functionCall would be rejected outright, so it is carried as
                    # text instead. The data stays real; only the framing changes.
                    parts.append({"text": _describe_tool_call(function)})
            if not parts:
                parts.append({"text": ""})
            contents.append({"role": "model", "parts": parts})
            continue

        # user
        contents.append({"role": "user", "parts": [{"text": content}]})

    # Gemini requires the first content to be a user turn.
    while contents and contents[0].get("role") == "model":
        contents.pop(0)
    if not contents:
        contents = [{"role": "user", "parts": [{"text": ""}]}]
    return contents, ("\n\n".join(system_parts) if system_parts else None)


def _describe_tool_call(function: dict) -> str:
    """Render a provider-foreign tool call as text for Gemini context."""
    name = function.get("name") or "tool"
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (ValueError, TypeError):
            pass
    return f'[tool call] {name}({json.dumps(arguments, default=str) if isinstance(arguments, dict) else arguments})'


def _parse_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def to_openai_tool_calls(parts: list[dict]) -> list[dict]:
    """Convert Gemini ``functionCall`` parts into OpenAI-style tool_calls.

    Gemini 3.x returns a ``thoughtSignature`` alongside each function call and
    rejects the follow-up request unless the same signature is echoed back, so
    it is carried through the normalized representation.
    """
    calls: list[dict] = []
    for index, part in enumerate(parts):
        call = part.get("functionCall")
        if not call:
            continue
        function: dict[str, Any] = {
            "name": call.get("name") or "tool",
            "arguments": _dump_args(call.get("args")),
        }
        signature = part.get("thoughtSignature") or call.get("thoughtSignature")
        if signature:
            function["thought_signature"] = signature
        calls.append({
            "id": f"gemini-{index}",
            "type": "function",
            "function": function,
        })
    return calls


def _dump_args(args: Any) -> str:
    import json

    try:
        return json.dumps(args if isinstance(args, dict) else {})
    except (ValueError, TypeError):
        return "{}"


def to_gemini_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-style tool definitions into Gemini functionDeclarations."""
    declarations = []
    for tool in tools or []:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not function:
            continue
        declaration: dict[str, Any] = {
            "name": function.get("name") or "tool",
            "description": function.get("description") or "",
        }
        parameters = function.get("parameters")
        if parameters:
            declaration["parameters"] = _clean_schema(parameters)
        declarations.append(declaration)
    return [{"functionDeclarations": declarations}] if declarations else []


#: JSON-Schema keywords Gemini's functionDeclarations accept. Everything else is
#: dropped, because Gemini rejects an *unknown field name* with HTTP 400 rather
#: than ignoring it. Pydantic v2 emits several of these by default
#: (``exclusiveMinimum`` for ``gt=``, ``default``, ``additionalProperties``).
_GEMINI_SCHEMA_KEYS = {
    "type", "format", "title", "description", "nullable", "enum",
    "maxItems", "minItems", "minimum", "maximum",
    "properties", "required", "items", "anyOf", "propertyOrdering",
}


def _clean_schema(schema: Any) -> Any:
    """Reduce a Pydantic JSON schema to the subset Gemini accepts.

    Unknown keys are removed rather than renamed: Gemini's error names the exact
    field, so an unrecognised keyword fails the whole request. ``anyOf`` (used by
    Pydantic for ``Optional[...]``) is preserved.
    """
    if isinstance(schema, list):
        return [_clean_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        # Pydantic emits ``exclusiveMinimum``/``exclusiveMaximum`` for ``gt=``
        # and ``lt=``; Gemini's OpenAPI subset has no such field. Convert to the
        # inclusive equivalent so the bound survives instead of vanishing.
        if key == "exclusiveMinimum":
            cleaned["minimum"] = value
            continue
        if key == "exclusiveMaximum":
            cleaned["maximum"] = value
            continue
        if key not in _GEMINI_SCHEMA_KEYS:
            continue
        if key == "properties":
            # A map of field name -> schema. The names are data, not schema
            # keywords, so they must survive even though they are not in the
            # allowed-keyword set.
            cleaned[key] = {
                name: _clean_schema(field) for name, field in value.items()
            } if isinstance(value, dict) else {}
            continue
        if key == "anyOf":
            # Flatten a nullable union into a nullable single type where possible:
            # smaller, and unambiguous for Gemini.
            options = [_clean_schema(option) for option in value if isinstance(option, dict)]
            non_null = [option for option in options if option.get("type") != "null"]
            has_null = any(option.get("type") == "null" for option in options)
            if has_null and len(non_null) == 1:
                cleaned.update(non_null[0])
                cleaned["nullable"] = True
                continue
            if non_null:
                cleaned["anyOf"] = non_null
                continue
            if options:
                cleaned["anyOf"] = options
            continue
        cleaned[key] = _clean_schema(value) if isinstance(value, (dict, list)) else value
    return cleaned


class GeminiProvider:
    """Adapter for the Gemini ``generateContent`` endpoint."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        max_output_tokens: int = 8192,
        thinking_budget: int | None = 1024,
    ) -> None:
        self.provider = "gemini"
        self.name = "gemini"
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.max_output_tokens = max_output_tokens
        # Gemini's "flash" models spend part of the output budget on internal
        # reasoning. Without an explicit budget a small maxOutputTokens yields
        # an empty completion (finishReason=MAX_TOKENS), which would look like a
        # provider failure. Bounding it keeps answers inside the token budget.
        self.thinking_budget = thinking_budget
        self.pricing = GEMINI_PRICING

    def chat(self, messages: list[dict], tools: list[dict], *, max_tokens: int,
             structured: bool = False, model: str | None = None) -> ChatResult:
        effective_model = model or self.model
        contents, system_instruction = to_gemini_contents(messages)
        # Never ask for less than the thinking budget plus room for an answer.
        effective_tokens = max(int(max_tokens), 256)
        effective_tokens = min(effective_tokens, self.max_output_tokens)
        generation_config: dict[str, Any] = {
            "maxOutputTokens": effective_tokens,
            "temperature": 0.1,
        }
        if self.thinking_budget is not None:
            # Leave at least 128 tokens for the visible answer.
            budget = min(self.thinking_budget, max(0, effective_tokens - 128))
            if budget > 0:
                generation_config["thinkingConfig"] = {"thinkingBudget": budget}
        if structured:
            generation_config["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {"contents": contents, "generationConfig": generation_config}
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        gemini_tools = to_gemini_tools(tools)
        if gemini_tools:
            payload["tools"] = gemini_tools

        url = f"{self.base_url}/models/{effective_model}:generateContent"
        started = time.perf_counter()
        with httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds),
            transport=self.transport,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.post(
                url,
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
            )
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        if response.status_code >= 400:
            logger.error(
                "ai_provider_http_error provider=gemini model=%s status=%s",
                effective_model, response.status_code,
            )
            response.raise_for_status()

        try:
            body = response.json()
            candidate = (body.get("candidates") or [])[0]
            parts = (candidate.get("content") or {}).get("parts") or []
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("gemini returned an invalid completion") from exc

        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        tool_calls = to_openai_tool_calls(parts)
        usage = body.get("usageMetadata") or {}
        prompt_tokens = int(usage.get("promptTokenCount") or 0)
        completion_tokens = int(usage.get("candidatesTokenCount") or 0)
        return ChatResult(
            message=ChatMessage(content=text, tool_calls=tool_calls,
                                raw={"finishReason": candidate.get("finishReason")}),
            model=effective_model,
            provider="gemini",
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(usage.get("totalTokenCount") or (prompt_tokens + completion_tokens)),
            estimated_cost_usd=0.0,
        )

    def capabilities(self) -> ProviderCapabilities:
        caps = ProviderCapabilities(
            provider="gemini",
            model=effective_model,
            max_output_tokens=self.max_output_tokens,
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
            cost_tier="free",
        )
        started = time.perf_counter()
        try:
            result = self.chat(
                [{"role": "user", "content": "Reply with the single word: ok"}],
                [], max_tokens=PROBE_MAX_TOKENS,
            )
            caps.chat = bool(result.message.content.strip())
        except Exception as exc:  # noqa: BLE001 - a probe must never raise
            caps.error = _safe_error(exc)
            return caps
        caps.latency_ms = round((time.perf_counter() - started) * 1000, 1)

        try:
            result = self.chat(
                [{"role": "user", "content": "What is the weather in Paris? Use the tool."}],
                [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get the weather for a city",
                        "parameters": {"type": "object",
                                       "properties": {"city": {"type": "string"}},
                                       "required": ["city"]},
                    },
                }],
                max_tokens=PROBE_MAX_TOKENS,
            )
            caps.tool_calling = bool(result.message.tool_calls)
        except Exception as exc:  # noqa: BLE001
            caps.tool_calling = False

        try:
            self.chat(
                [{"role": "user", "content": 'Return JSON with a "status" key set to "ok".'}],
                [], max_tokens=PROBE_MAX_TOKENS, structured=True,
            )
            caps.structured_output = True
        except Exception as exc:  # noqa: BLE001
            caps.structured_output = False
        return caps


def _safe_error(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (400, 403):
        return "request rejected (check the API key or model id)"
    if status == 429:
        return "rate limited or quota exhausted"
    if status == 404:
        return "model not available for this key"
    if status is not None:
        return f"provider returned HTTP {status}"
    return f"{type(exc).__name__}"
