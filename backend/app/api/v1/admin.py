"""RealEstateGPT - Admin API routes.

Every route in this module requires the server-side ``admin`` role. No route
here ever trusts a client-supplied role flag.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_db
from app.core.security import get_current_admin
from app.repositories.platform_repo import AuditRepository, AIConversationRepository
from app.repositories.property_repo import PropertyRepository
from app.repositories.user_repo import UserRepository
from app.repositories.saved_repo import SavedRepository
from app.schemas import AdminStatsResponse, AdminPropertyListResponse, AdminPropertyItemResponse
from app.schemas.documents_admin import (
    AdminAiUsageResponse, AdminUserListResponse, AdminUserResponse,
    AuditLogResponse,
)
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Get admin dashboard statistics."""
    prop_repo = PropertyRepository(db)
    user_repo = UserRepository(db)
    saved_repo = SavedRepository(db)
    ai_repo = AIConversationRepository(db)

    return AdminStatsResponse(
        total_properties=prop_repo.count(),
        active_properties=prop_repo.count(active_only=True),
        verified_properties=prop_repo.count(verified_only=True),
        total_users=user_repo.count(),
        total_saved_properties=saved_repo.count_saved(),
        total_saved_searches=saved_repo.count_saved_searches(),
        total_comparisons=saved_repo.count_comparisons(),
        total_searches=saved_repo.count_searches(),
        total_ai_messages=ai_repo.count_messages(),
        total_documents=db["documents"].count_documents({}),
        total_recommendations=db["recommendations"].count_documents({}),
        properties_by_city=prop_repo.count_by_city(),
        properties_by_type=prop_repo.count_by_type(),
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """List user accounts (admin only)."""
    repo = UserRepository(db)
    skip = (page - 1) * page_size
    users = repo.list_all(skip=skip, limit=page_size)
    total = repo.count()
    return AdminUserListResponse(
        users=[AdminUserResponse.model_validate(u) for u in users], total=total
    )


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_admin_user(
    user_id: int,
    role: Optional[str] = Query(None, pattern="^(user|admin|agent)$"),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Update a user's role or active status (admin only, self-protection)."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot modify your own account here.")
    repo = UserRepository(db)
    updates: dict = {}
    if role is not None:
        updates["role"] = role
    if is_active is not None:
        updates["is_active"] = is_active
    if not updates:
        raise HTTPException(status_code=422, detail="Nothing to update.")
    updated = repo.update(user_id, **updates)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserResponse.model_validate(updated)


@router.get("/web-discovery")
async def admin_web_discovery_status(
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Admin view of the web discovery layer (sources + provider health + cache)."""
    from app.core.config import settings
    from app.discovery.sources import get_sources
    from app.providers.web_search.registry import web_search_health

    health = web_search_health().snapshot().model_dump()
    health["configured"] = settings.web_search_configured
    health["enabled"] = settings.WEB_DISCOVERY_ENABLED

    sources = [
        {
            "name": source.name,
            "domain": source.domain,
            "enabled": source.enabled,
            "discovery_allowed": source.discovery_allowed,
            "page_fetch_allowed": source.page_fetch_allowed,
            "requires_permission": source.requires_permission,
            "categories": list(source.categories),
        }
        for source in get_sources()
    ]

    counts = {}
    try:
        counts["discoveries"] = db["web_property_discoveries"].count_documents({})
        counts["cache_entries"] = db["web_search_cache"].count_documents({})
        counts["expired_cache"] = db["web_search_cache"].count_documents({"expires_at": {"$lt": datetime.now(timezone.utc)}})
        counts["recent_discoveries"] = db["web_property_discoveries"].count_documents({"discovered_at": {"$gt": datetime.now(timezone.utc) - timedelta(hours=24)}})
    except Exception as exc:  # noqa: BLE001 - admin endpoint must not fail
        counts["error"] = str(exc)[:200]

    return {
        "provider": health,
        "sources": sources,
        "config": {
            "max_queries": settings.WEB_SEARCH_MAX_QUERIES,
            "max_results": settings.WEB_SEARCH_MAX_RESULTS,
            "cache_ttl_seconds": settings.WEB_SEARCH_CACHE_TTL_SECONDS,
            "osm_enrich_limit": settings.WEB_DISCOVERY_OSM_ENRICH_LIMIT,
            "allowed_domains": settings.web_search_allowed_domains,
        },
        "collections": counts,
        "message": "Web discovery results are short-lived and never presented as verified inventory.",
    }
@router.get("/properties", response_model=AdminPropertyListResponse)
async def list_admin_properties(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """List properties including provenance/quality metadata (admin only)."""
    repo = PropertyRepository(db)
    skip = (page - 1) * page_size
    query: dict = {} if include_inactive else {"is_active": True}
    cursor = repo.coll.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    rows = list(cursor)
    total = repo.coll.count_documents(query)
    items = []
    for doc in rows:
        items.append(AdminPropertyItemResponse(
            id=doc["_id"],
            title=doc.get("title", ""),
            city=doc.get("city", ""),
            locality=doc.get("locality"),
            price=doc.get("price", 0),
            property_type=doc.get("property_type", ""),
            verification_status=doc.get("verification_status", "unverified"),
            is_active=doc.get("is_active", True),
            is_synthetic=doc.get("is_synthetic", True),
            created_at=doc.get("created_at"),
        ))
    total_pages = max(1, (total + page_size - 1) // page_size)
    return AdminPropertyListResponse(properties=items, total=total, page=page,
                                     page_size=page_size, total_pages=total_pages)


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Recent audit trail entries (admin only)."""
    return AuditRepository(db).list(limit=limit, offset=offset)


@router.get("/ai-usage", response_model=AdminAiUsageResponse)
async def admin_ai_usage(
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """AI usage aggregates (admin only)."""
    from app.core.config import settings

    ai_repo = AIConversationRepository(db)
    audit = AuditRepository(db)
    by_action = audit.count_by_action(limit=20)
    ai_actions = {k: v for k, v in by_action.items() if k.startswith("ai.")}
    return AdminAiUsageResponse(
        total_messages=ai_repo.count_messages(),
        total_conversations=ai_repo.count_conversations(),
        tool_calls=sum(ai_actions.values()),
        offline_mode=False,
        provider=settings.AI_PROVIDER,
        by_action=ai_actions,
    )


@router.put("/properties/{property_id}/verify")
async def verify_property(
    property_id: int,
    status_name: str = Query("verified", alias="status", pattern="^(verified|unverified|rejected)$"),
    current_user: User = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Verify or reject a property listing."""
    prop_repo = PropertyRepository(db)
    prop = prop_repo.verify_property(property_id, status_name)
    if not prop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    return {"message": f"Property {property_id} status updated to {status_name}"}
