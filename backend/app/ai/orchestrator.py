"""Compatibility orchestration facade for the grounded assistant."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.platform_repo import AIConversationRepository, AuditRepository
from app.schemas.ai import AssistantRequest, AssistantResponse, Citation
from app.services.ai_search_service import AiSearchService


class AssistantOrchestrator:
    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, user, request: AssistantRequest, ip: str | None = None) -> AssistantResponse:
        conversations = AIConversationRepository(self.db)
        conversation = conversations.get(request.conversation_id, user.id) if request.conversation_id else None
        if request.conversation_id and conversation is None:
            raise ValueError("conversation_not_found")
        conversation = conversation or conversations.create(user.id, request.message[:80], request.property_id)
        conversations.add_message(conversation.id, "user", request.message)
        search = AiSearchService(self.db).search(request.message, request.limit)
        results = search["results"]
        if results:
            answer = "I found these grounded matches:\n\n" + "\n".join(
                f"{index}. {item.title} — ₹{item.price:,.0f} — {item.overall_score:.0f}% match"
                for index, item in enumerate(results[:3], 1))
        else:
            answer = "I couldn't find an exact match. Try widening the budget or relaxing one requirement."
        conversations.add_message(conversation.id, "assistant", answer, {"route": "search"})
        AuditRepository(self.db).log("ai.message", user.id, "conversation", conversation.id, {"result_count": len(results)}, ip)
        return AssistantResponse(conversation_id=conversation.id, answer=answer,
            citations=[Citation(source_type="property", source_id=item.property_id, label=item.title) for item in results[:5]],
            parsed_query=search["parsed"], results=results, provider="offline",
            warnings=[search["warning"]] if search["warning"] else [])
