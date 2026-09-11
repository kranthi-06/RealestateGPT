"""RealEstateGPT Backend - Core Configuration"""

from pydantic_settings import BaseSettings
from typing import List, Optional
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "RealEstateGPT"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # MongoDB Atlas
    MONGODB_URI: str = ""  # required in production, e.g. mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/
    MONGODB_DATABASE: str = "realestate_gpt"
    MONGODB_CONNECT_TIMEOUT_MS: int = 10_000
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 10_000
    MONGODB_SOCKET_TIMEOUT_MS: int = 30_000
    MONGODB_MAX_POOL_SIZE: int = 20

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

    # AI provider: offline | groq
    AI_PROVIDER: str = "offline"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "qwen/qwen3.8-27b"  # verified in docs/AI_MODEL_SELECTION.md
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    AI_TIMEOUT_SECONDS: int = 60
    AI_MAX_TOKENS: int = 1200
    MAX_AGENT_STEPS: int = 3
    MAX_TOOL_CALLS: int = 5
    AI_RATE_LIMIT_REQUESTS: int = 12
    AI_RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Embeddings
    #   local  = lightweight hashed TF-IDF vectors, works fully offline
    #   openai = remote embeddings via an OpenAI-compatible API
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    AI_API_KEY: Optional[str] = None  # legacy: OpenAI-compatible embeddings key
    AI_BASE_URL: Optional[str] = None

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

    # Location intelligence
    #   osm    = OpenStreetMap (Nominatim + Overpass + OSRM) - default, no billing
    #   google = Google Maps Platform (requires Google Cloud billing)
    LOCATION_PROVIDER: str = "osm"
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    OVERPASS_URL: str = "https://overpass-api.de/api/interpreter"
    OSRM_BASE_URL: str = "https://router.project-osrm.org"
    NOMINATIM_USER_AGENT: str = "RealEstateGPT/1.0"
    OSM_TIMEOUT_SECONDS: int = 15
    MAPS_PROVIDER: str = "none"  # google | none (optional, requires billing)
    GOOGLE_MAPS_SERVER_KEY: Optional[str] = None
    GOOGLE_MAPS_TIMEOUT_SECONDS: int = 10

    # Background jobs
    REDIS_URL: Optional[str] = None

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

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
        return self.AI_PROVIDER == "groq" and bool(self.GROQ_API_KEY)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
