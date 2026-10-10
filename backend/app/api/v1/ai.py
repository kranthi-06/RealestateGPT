"""Grounded AI search and conversation endpoints.

Responses are composed only from records retrieved from the application
database. The request text is never treated as instructions for database or
tool access.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.database import get_db
from app.core.security import get_current_admin, get_current_user, get_optional_user
from app.ai.gateway import AIError
from app.ai.orchestrator import AssistantOrchestrator
from app.ai.registry import get_registry
from app.core.ai_rate_limit import ai_rate_limiter
from app.repositories.platform_repo import AIConversationRepository, AuditRepository
from app.schemas.ai import AiSearchRequest, AiSearchResponse, AssistantRequest, AssistantResponse, MessageResponse, ConversationSummary
from app.services.ai_search_service import AiSearchService

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/search", response_model=AiSearchResponse)
async def ai_search(data: AiSearchRequest, db=Depends(get_db), user=Depends(get_optional_user)):
    """Parse a natural-language request and return explainably ranked properties."""
    result = AiSearchService(db).search(data.query, data.limit, data.user_filters)
    AuditRepository(db).log("ai.search", user.id if user else None, "search",
                            detail={"query_length": len(data.query), "results": result["total"]})
    return result


@router.post("/assistant", response_model=AssistantResponse)
async def assistant(data: AssistantRequest, request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    """Use the configured Groq provider and its closed tool registry."""
    key = str(user.id)
    try:
        ai_rate_limiter.check(key)
    except AIError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
            headers={"Retry-After": str(ai_rate_limiter.retry_after_seconds(key))},
        ) from exc
    # The agent performs blocking provider I/O and database reads; running it in
    # a worker thread keeps the event loop free for every other request.
    from fastapi.concurrency import run_in_threadpool

    try:
        return await run_in_threadpool(
            AssistantOrchestrator(db).run, user, data,
            request.client.host if request.client else None,
        )
    except AIError as exc:
        # A provider-level failure is reported honestly; no response is fabricated.
        # Configuration and availability errors never consumed a provider slot.
        if exc.code in {"AI_CONFIGURATION_ERROR", "AI_ALL_PROVIDERS_UNAVAILABLE"}:
            ai_rate_limiter.release(key, consumed=False)
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
            headers={"Retry-After": "20"} if exc.status_code == 429 else None,
        ) from exc
    except ValueError as exc:
        if str(exc) == "conversation_not_found":
            ai_rate_limiter.release(key, consumed=False)
            raise HTTPException(status_code=404, detail="Conversation not found")
        ai_rate_limiter.release(key, consumed=False)
        raise
    except Exception:
        # The provider was attempted, so the quota stays consumed.
        raise
    else:
        ai_rate_limiter.release(key, consumed=True)


@router.get("/providers/status")
async def provider_status(db=Depends(get_db), user=Depends(get_current_user)):
    """Credential-free AI provider health snapshot.

    Reports which providers are configured, which model each uses, whether it
    is available, and aggregate request/latency/cost counters. Never returns an
    API key, a token, or any request content.
    """
    registry = get_registry()
    # Probe lazily: the first status call verifies each configured provider.
    registry.probe_all()
    status = registry.status()
    primary = registry.ordered()
    status["primary"] = primary[0].name if primary else None
    status["primary_model"] = getattr(primary[0].provider, "model", None) if primary else None
    status["fallback_order"] = [entry.name for entry in primary[1:]]
    return status


@router.post("/providers/probe")
async def probe_providers(user=Depends(get_current_admin)):
    """Re-verify every provider's live capabilities (admin only)."""
    registry = get_registry()
    registry.probe_all(force=True)
    return registry.status()


@router.get("/conversations", response_model=list[ConversationSummary])
async def conversations(db=Depends(get_db), user=Depends(get_current_user)):
    rows = AIConversationRepository(db).list_for_user(user.id)
    return [ConversationSummary(id=row.id, title=row.title, property_id=row.property_id,
            updated_at=row.updated_at, message_count=len(row.messages)) for row in rows]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def messages(conversation_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    repo = AIConversationRepository(db)
    if not repo.get(conversation_id, user.id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return [MessageResponse.model_validate(row) for row in repo.messages(conversation_id)]
