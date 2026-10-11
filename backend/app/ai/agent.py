"""RealEstateGPT Conversational AI Assistant.

Provides expert, natural conversational real estate guidance: property search,
home loans, EMI calculation, rental yields, affordability, and market insights.
Operates independently of mandatory database queries.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.ai.gateway import AIValidationError, AIGateway, get_gateway
from app.ai.tool_registry import ToolRegistry
from app.core.config import settings
from app.schemas.ai import Citation, ScoredProperty, ToolCallRecord

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are RealEstateGPT, an expert conversational AI assistant specializing in real estate, property markets, home buying, renting, mortgages, affordability, and investments.
You converse naturally and helpfully like ChatGPT, with deep real-estate and financial domain knowledge.

Guidelines:
- Greetings & General Chat: When greeted (e.g. "Hii", "Hello") or asked general questions, reply warmly, introduce yourself, and highlight key real estate topics you can assist with (property search, home loans, EMI calculations, rental yield, affordability, locality trends).
- Real Estate Concepts: Provide clear, accessible, and structured explanations for concepts like rental yields (gross vs. net, calculation formula, illustrative example), home loans (principal, interest, tenure, down payment, EMI), capital appreciation, RERA, stamp duty, etc.
- Affordability & Budget: For affordability questions (e.g. "Can I afford a house worth ₹60 lakh?"), outline key factors (monthly income, existing debts, down payment savings, loan tenure, interest rate) and provide realistic estimates or ask for missing details.
- Locality & Market Guidance: For locality queries (e.g. "What is a good location to buy a house in Hyderabad?"), explain key comparison criteria (connectivity, tech corridors, infrastructure, budget brackets) and recommend prominent areas.
- Specific Property Inquiries: If asked to find properties or rentals in a town or city (e.g. "Find a 2 BHK for rent in Nandyal"), respond conversationally: acknowledge the location, explain typical price/rent ranges, provide practical advice on finding local listings, and explain that you provide market guidance. Never fabricate fake property listings or fake IDs.
- Follow-ups: Retain context from previous messages and answer follow-up questions smoothly and naturally.
- Formatting: Use clean Markdown formatting with clear bullet points, bold key terms, and section headers where appropriate.
"""


class FinalAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)
    property_ids: list[int] = Field(default_factory=list, max_length=20)
    follow_up_suggestions: list[str] = Field(default_factory=list, max_length=3)


class AgentResult(BaseModel):
    answer: str
    results: list[ScoredProperty] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    provider: str = "groq"
    parsed_query: Any = None
    warning: str | None = None
    trace: dict = Field(default_factory=dict)


MAX_TOOL_PAYLOAD_CHARS = 6000


def _bounded_tool_payload(result: object) -> str:
    """Serialize a tool result, truncating rather than failing the request."""
    try:
        text = json.dumps(result, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        text = json.dumps({"status": "unserializable"}, separators=(",", ":"))
    if len(text) <= MAX_TOOL_PAYLOAD_CHARS:
        return text
    logger.info("tool_payload_truncated chars=%s limit=%s", len(text), MAX_TOOL_PAYLOAD_CHARS)
    return text[:MAX_TOOL_PAYLOAD_CHARS] + "…[truncated]"


class GroqToolCallingAgent:
    """Conversational assistant with optional tool execution."""

    def __init__(self, db, user, provider: Any | None = None, registry: ToolRegistry | None = None) -> None:
        self.db, self.user = db, user
        self.registry = registry or ToolRegistry()
        self._provider_override = provider

    def run(self, message: str, conversation_context: list[dict]) -> AgentResult:
        gateway = self._provider_override or get_gateway()
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for item in conversation_context[-8:]:
            if item.get("role") in {"user", "assistant"}:
                messages.append({"role": item["role"], "content": item.get("content", "")[:4000]})
        messages.append({"role": "user", "content": message})

        records: list[ToolCallRecord] = []
        search_payload: dict | None = None
        total_provider_ms = 0.0
        provider_used = "unknown"
        final_answer_text = ""

        definitions = self.registry.definitions() if self.registry else []

        for step in range(settings.MAX_AGENT_STEPS):
            completion = gateway.generate_with_tools(messages, definitions)
            total_provider_ms += completion.get("latency_ms", 0.0)
            provider_used = completion.get("provider", provider_used)
            model_message = completion.get("message") or {}
            calls = model_message.get("tool_calls") or []
            content = model_message.get("content") or ""

            # If the model returned direct conversational text without requesting tools, return it directly
            if not calls:
                if content.strip():
                    final_answer_text = content.strip()
                break

            messages.append({"role": "assistant", "content": content, "tool_calls": calls})

            if len(records) + len(calls) > settings.MAX_TOOL_CALLS:
                logger.info("agent_tool_limit_reached calls=%s completed=%s", len(calls), len(records))
                break

            for call in calls:
                function = call.get("function") or {}
                name, arguments = function.get("name"), function.get("arguments", "{}")
                try:
                    result, _ = self.registry.execute(self.db, self.user, name, arguments)
                    logger.info("tool_call tool=%s status=ok", name)
                except Exception as exc:
                    logger.warning("tool_call tool=%s status=error message=%s", name, str(exc))
                    result = {"status": "unavailable", "message": f"Data temporarily unavailable for {name}"}

                if name in {"search_properties", "get_property", "search_web_properties"} and isinstance(result, dict):
                    search_payload = result

                records.append(ToolCallRecord(tool=name, input=self._safe_input(arguments), output_summary=self._summary(name, result)))
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "name": name,
                    "content": _bounded_tool_payload(result),
                })

        # Synthesize final answer if not already set (e.g. tools were called, or test with mock provider)
        if not final_answer_text:
            final_messages: list[dict] = []
            for item in messages:
                if item.get("role") not in {"system", "user", "assistant", "tool"}:
                    continue
                kept = {"role": item.get("role"), "content": item.get("content") or ""}
                if item.get("role") == "tool":
                    kept["tool_call_id"] = item.get("tool_call_id", "")
                final_messages.append(kept)

            # Support structured output if provider supports it (for mock providers and schema grounding)
            if hasattr(gateway, "generate_structured"):
                try:
                    final = gateway.generate_structured(
                        final_messages, "grounded_assistant_response", FinalAnswer.model_json_schema()
                    )
                    total_provider_ms += final.get("latency_ms", 0.0)
                    final_ans = FinalAnswer.model_validate_json(final["message"].get("content") or "{}")
                    return self._ground(final_ans, search_payload, records, total_provider_ms, provider_used)
                except Exception as exc:
                    logger.warning("structured_final_answer_fallback: %s", exc)

            final_messages.append({
                "role": "system",
                "content": "Please synthesize a helpful, conversational answer for the user based on the tool results above.",
            })
            try:
                summary = gateway.chat(final_messages, [], complexity="fast")
                total_provider_ms += summary.latency_ms
                provider_used = summary.provider
                final_answer_text = summary.message.content.strip()
            except Exception as exc:
                logger.warning("conversational_synthesis_fallback: %s", exc)
                final_answer_text = "Here is the relevant real estate information for your request. How else can I assist you today?"

        final_answer = FinalAnswer(answer=final_answer_text, property_ids=[], follow_up_suggestions=[])
        return self._ground(final_answer, search_payload, records, total_provider_ms, provider_used)

    @staticmethod
    def _safe_input(raw: str | dict) -> dict:
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}

    @staticmethod
    def _summary(name: str, result: dict) -> str:
        if name == "search_properties":
            return f"{result.get('total', 0)} candidates"
        if name == "get_property":
            return f"{len(result.get('properties', []))} property records"
        if name == "nearby_places":
            return f"{len(result.get('places', []))} places"
        if name == "search_web_properties":
            return f"{len(result.get('results', []))} web discoveries"
        return "tool executed"

    @staticmethod
    def _ground(final: FinalAnswer, search: dict | None, records: list[ToolCallRecord],
                provider_ms: float, provider_used: str = "unknown") -> AgentResult:
        results = (search or {}).get("results", [])
        typed_results = [item if isinstance(item, ScoredProperty) else ScoredProperty.model_validate(item) for item in results]
        allowed_ids = {item.property_id for item in typed_results}
        requested_ids = [property_id for property_id in final.property_ids if property_id in allowed_ids]
        visible = [item for item in typed_results if not requested_ids or item.property_id in requested_ids]

        citations = []
        for item in visible[:5]:
            citations.append(Citation(source_type="property", source_id=item.property_id, label=item.title))
        for disc in (search or {}).get("discoveries", [])[:3]:
            citations.append(Citation(source_type="web", label=disc.get("title", "Web listing"), url=disc.get("url")))

        return AgentResult(
            answer=final.answer,
            results=visible,
            citations=citations,
            tool_calls=records,
            parsed_query=(search or {}).get("parsed"),
            warning=(search or {}).get("warning"),
            trace={
                "model": f"{provider_used}",
                "provider": provider_used,
                "tool_call_count": len(records),
                "provider_latency_ms": provider_ms,
                "candidate_count": (search or {}).get("total", len(visible)),
            },
        )
