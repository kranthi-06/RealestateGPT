"""RealEstateGPT - Health check API routes"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from datetime import datetime, timezone
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """Basic health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "RealEstateGPT API",
        "version": "1.0.0",
    }


@router.get("/db")
async def database_health(db: Session = Depends(get_db)):
    """Database health check."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


@router.get("/ai")
async def ai_health():
    """Report the configured grounded-search/LLM capability."""
    return {
        "status": "healthy",
        "provider": settings.AI_PROVIDER,
        "configured": settings.ai_configured,
        "message": "Grounded deterministic search is available; external LLM is optional.",
    }
