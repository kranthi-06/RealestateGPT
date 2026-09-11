"""Conversation persistence plus the grounded Groq agent."""
from __future__ import annotations

import logging

from app.ai.agent import GroqToolCallingAgent
from app.repositories.platform_repo import AIConversationRepository, AuditRepository
from app.schemas.ai import AssistantRequest, AssistantResponse

logger = logging.getLogger(__name__)


class AssistantOrchestrator:
    def __init__(self, db) -> None:
        self.db = db

    def run(self, user, request: AssistantRequest, ip: str | None = None) -> AssistantResponse:
        conversations = AIConversationRepository(self.db)
        conversation = conversations.get(request.conversation_id, user.id) if request.conversation_id else None
        if request.conversation_id and conversation is None:
            raise ValueError("conversation_not_found")
        conversation = conversation or conversations.create(user.id, request.message[:80], request.property_id)
        context = [{"role": row.role, "content": row.content} for row in conversations.messages(conversation.id)]
        conversations.add_message(conversation.id, "user", request.message)
        try:
            result = GroqToolCallingAgent(self.db, user).run(request.message, context)
        except Exception as exc:
            AuditRepository(self.db).log("ai.message.failed", user.id, "conversation", conversation.id,
                                         {"error_category": getattr(exc, "code", "AI_PROVIDER_ERROR")}, ip)
            raise
        meta = {"tool_calls": [item.model_dump() for item in result.tool_calls], "citations": [item.model_dump() for item in result.citations],
                "parsed_query": result.parsed_query.model_dump() if result.parsed_query else None, "trace": result.trace,
                "result_ids": [item.property_id for item in result.results]}
        conversations.add_message(conversation.id, "assistant", result.answer, meta)
        AuditRepository(self.db).log("ai.message", user.id, "conversation", conversation.id, result.trace, ip)
        logger.info("ai_execution conversation_id=%s user_id=%s model=%s tools=%s latency_ms=%s candidates=%s",
                    conversation.id, user.id, result.trace.get("model"), result.trace.get("tool_call_count"),
                    result.trace.get("provider_latency_ms"), result.trace.get("candidate_count"))
        return AssistantResponse(conversation_id=conversation.id, answer=result.answer, citations=result.citations,
                                 tool_calls=result.tool_calls, parsed_query=result.parsed_query, results=result.results,
                                 provider=result.provider, warnings=[result.warning] if result.warning else [])
