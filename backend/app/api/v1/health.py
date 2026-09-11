"""RealEstateGPT - Health check API routes"""

from fastapi import APIRouter, Depends
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import get_db, ping

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """Basic health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "RealEstateGPT API",
        "version": "1.1.0",
    }


@router.get("/db")
async def database_health(db=Depends(get_db)):
    """Database health check: reports real MongoDB connectivity (no silent fallback)."""
    try:
        ok = ping()
        return {"status": "healthy" if ok else "unhealthy", "database": "mongodb"}
    except Exception as exc:
        return {"status": "unhealthy", "database": "mongodb", "error": str(exc)}


@router.get("/ai")
async def ai_health():
    """Report the configured AI capability."""
    return {
        "status": "healthy",
        "provider": settings.AI_PROVIDER,
        "configured": settings.ai_configured,
        "message": "Groq tool-calling is available only when AI_PROVIDER=groq and GROQ_API_KEY is configured.",
    }
