"""RealEstateGPT Backend - Core Configuration"""

from pydantic_settings import BaseSettings
from typing import List, Optional
import os
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "RealEstateGPT"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "sqlite:///./realestate_gpt.db"

    # Security
    SECRET_KEY: str = "change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Rate limiting (simple in-memory window limiter)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 60  # per window
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_AUTH_REQUESTS: int = 10  # stricter for /auth endpoints

    # AI provider
    #   offline = deterministic grounded responses, no external API required
    #   openai  = OpenAI-compatible chat completions (works with OpenAI, Ollama, etc.)
    AI_PROVIDER: str = "offline"
    AI_API_KEY: Optional[str] = None
    AI_MODEL: str = "gpt-4o-mini"
    AI_BASE_URL: Optional[str] = None  # e.g. http://localhost:11434/v1 for Ollama
    AI_TIMEOUT_SECONDS: int = 60

    # Embeddings
    #   local  = lightweight hashed TF-IDF vectors, works fully offline
    #   openai = remote embeddings via API
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Recommendation scoring weights (must sum to 100)
    SCORING_WEIGHTS_JSON: str = (
        '{"budget": 25, "location": 20, "property_type": 15, '
        '"connectivity": 15, "amenities": 10, "area": 5, '
        '"lifestyle": 5, "price_fairness": 5}'
    )

    # ML price estimation
    ML_ARTIFACTS_DIR: str = "./data/artifacts"
    ML_TRAIN_ON_STARTUP: bool = False
    ML_MIN_SAMPLES: int = 20  # below this, fall back to heuristic estimates

    # Storage (documents & images)
    STORAGE_PROVIDER: str = "local"  # local | s3
    STORAGE_LOCAL_DIR: str = "./data/uploads"
    S3_BUCKET: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None

    # Google Maps Platform. The server key is strictly backend-only.
    MAPS_PROVIDER: str = "none"  # none | google
    GOOGLE_MAPS_SERVER_KEY: Optional[str] = None
    GOOGLE_MAPS_TIMEOUT_SECONDS: int = 10

    # Background jobs
    REDIS_URL: Optional[str] = None

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def scoring_weights(self) -> dict:
        try:
            weights = json.loads(self.SCORING_WEIGHTS_JSON)
            total = sum(float(v) for v in weights.values())
            # Normalize to 100 so partial weights still behave predictably.
            if total > 0:
                weights = {
                    k: round((float(v) / total) * 100, 2) for k, v in weights.items()
                }
            return {k: float(v) for k, v in weights.items()}
        except (ValueError, TypeError):
            return {
                "budget": 25.0, "location": 20.0, "property_type": 15.0,
                "connectivity": 15.0, "amenities": 10.0, "area": 5.0,
                "lifestyle": 5.0, "price_fairness": 5.0,
            }

    @property
    def ai_configured(self) -> bool:
        """True when a real LLM API is available for generative responses."""
        return self.AI_PROVIDER == "openai" and bool(self.AI_API_KEY)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
