"""Grounded AI search and conversation endpoints.

Responses are composed only from records retrieved from the application
database. The request text is never treated as instructions for database or
tool access.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.database import get_db
from app.core.security import get_current_user, get_optional_user
from app.ai.gateway import AIError
from app.ai.orchestrator import AssistantOrchestrator
from app.core.ai_rate_limit import ai_rate_limiter
from app.repositories.platform_repo import AIConversationRepository, AuditRepository
from app.schemas.ai import AiSearchRequest, AiSearchResponse, AssistantRequest, AssistantResponse, MessageResponse, ConversationSummary
from app.services.ai_search_service import AiSearchService

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/search", response_model=AiSearchResponse)
async def ai_search(data: AiSearchRequest, db = Depends(get_db), user=Depends(get_optional_user)):
    """Parse a natural-language request and return explainably ranked properties."""
    result = AiSearchService(db).search(data.query, data.limit, data.user_filters)
    AuditRepository(db).log("ai.search", user.id if user else None, "search", detail={"query_length": len(data.query), "results": result["total"]})
    return result


@router.post("/assistant", response_model=AssistantResponse)
async def assistant(data: AssistantRequest, request: Request, db = Depends(get_db), user=Depends(get_current_user)):
    """Use the configured Groq provider and its closed tool registry."""
    try:
        ai_rate_limiter.check(str(user.id))
        return AssistantOrchestrator(db).run(user, data, request.client.host if request.client else None)
    except AIError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": "AI search is temporarily unavailable. Please try again."})
    except ValueError as exc:
        if str(exc) == "conversation_not_found":
            raise HTTPException(status_code=404, detail="Conversation not found")
        raise


@router.get("/conversations", response_model=list[ConversationSummary])
async def conversations(db = Depends(get_db), user=Depends(get_current_user)):
    rows = AIConversationRepository(db).list_for_user(user.id)
    return [ConversationSummary(id=row.id, title=row.title, property_id=row.property_id,
            updated_at=row.updated_at, message_count=len(row.messages)) for row in rows]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def messages(conversation_id: int, db = Depends(get_db), user=Depends(get_current_user)):
    repo = AIConversationRepository(db)
    if not repo.get(conversation_id, user.id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return [MessageResponse.model_validate(row) for row in repo.messages(conversation_id)]
