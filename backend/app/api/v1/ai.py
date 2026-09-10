"""Grounded AI search and conversation endpoints.

Responses are composed only from records retrieved from the application
database. The request text is never treated as instructions for database or
tool access.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, get_optional_user
from app.repositories.platform_repo import AIConversationRepository, AuditRepository
from app.schemas.ai import AiSearchRequest, AiSearchResponse, AssistantRequest, AssistantResponse, Citation, MessageResponse, ConversationSummary
from app.services.ai_search_service import AiSearchService

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/search", response_model=AiSearchResponse)
async def ai_search(data: AiSearchRequest, db: Session = Depends(get_db), user=Depends(get_optional_user)):
    """Parse a natural-language request and return explainably ranked properties."""
    result = AiSearchService(db).search(data.query, data.limit, data.user_filters)
    AuditRepository(db).log("ai.search", user.id if user else None, "search", detail={"query_length": len(data.query), "results": result["total"]})
    return result


def _search_answer(results) -> str:
    if not results:
        return "I couldn't find an exact match. Try widening the budget or relaxing one requirement."
    lines = [f"I found {len(results)} grounded match{'es' if len(results) != 1 else ''}:", ""]
    for index, item in enumerate(results[:3], 1):
        reasons = "; ".join(item.positive_factors[:2]) or item.explanation or "Matches your requested criteria."
        lines.append(f"{index}. {item.title} — INR {item.price:,.0f} — {item.overall_score:.0f}% match\n   Why: {reasons}")
    lines.append("\nScores are decision support, not legal or investment advice.")
    return "\n".join(lines)


@router.post("/assistant", response_model=AssistantResponse)
async def assistant(data: AssistantRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Persist a user conversation and answer a property-discovery request."""
    conversations = AIConversationRepository(db)
    if data.conversation_id:
        conversation = conversations.get(data.conversation_id, user.id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = conversations.create(user.id, data.message[:80], data.property_id)
    conversations.add_message(conversation.id, "user", data.message)
    search = AiSearchService(db).search(data.message, data.limit)
    results = search["results"]
    answer = _search_answer(results)
    conversations.add_message(conversation.id, "assistant", answer, {"route": "search", "result_ids": [item.property_id for item in results]})
    AuditRepository(db).log("ai.message", user.id, "conversation", conversation.id, {"result_count": len(results)}, request.client.host if request.client else None)
    return AssistantResponse(conversation_id=conversation.id, answer=answer,
        citations=[Citation(source_type="property", source_id=item.property_id, label=item.title) for item in results[:5]],
        parsed_query=search["parsed"], results=results, provider="offline",
        warnings=[search["warning"]] if search["warning"] else [])


@router.get("/conversations", response_model=list[ConversationSummary])
async def conversations(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = AIConversationRepository(db).list_for_user(user.id)
    return [ConversationSummary(id=row.id, title=row.title, property_id=row.property_id,
            updated_at=row.updated_at, message_count=len(row.messages)) for row in rows]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def messages(conversation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    repo = AIConversationRepository(db)
    if not repo.get(conversation_id, user.id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return [MessageResponse.model_validate(row) for row in repo.messages(conversation_id)]
