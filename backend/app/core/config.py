"""RealEstateGPT Backend - Core Configuration"""

from pydantic_settings import BaseSettings
from typing import List, Optional
import json
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

#: The real production frontend. Allowed by CORS out of the box so a deployed
#: backend is never accidentally locked out of its own origin.
PRODUCTION_FRONTEND_ORIGIN = "https://realestate-gpt-inky.vercel.app"

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}


def _hostname_of(url: str) -> str:
    """Best-effort hostname extraction that tolerates bare hosts and origins."""
    candidate = (url or "").strip()
    if not candidate:
        return ""
    if "//" not in candidate:
        candidate = "//" + candidate
    try:
        return (urlparse(candidate).hostname or "").lower()
    except ValueError:
        return ""


def is_loopback_url(url: str) -> bool:
    """True when a URL points at the local machine (never valid in production)."""
    return _hostname_of(url) in _LOOPBACK_HOSTS


_SENSITIVE_SETTING_NAMES = {
    "GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "AI_API_KEY",
    "TAVILY_API_KEY", "BRAVE_SEARCH_API_KEY", "GEOAPIFY_API_KEY",
    "GOOGLE_MAPS_SERVER_KEY", "S3_ACCESS_KEY", "S3_SECRET_KEY",
    "SECRET_KEY", "CRON_SECRET", "WORKER_RUN_SECRET", "SEARXNG_AUTH_TOKEN",
}


def _mask_value(value) -> str:
    """Render a value safe for logs: never reveal a credential."""
    text = str(value)
    if len(text) <= 8:
        return "***"
    return f"***({len(text)} chars)"


def _safe_settings_validation_error(exc: Exception) -> ValueError:
    """Re-raise a settings error with every credential masked.

    Pydantic echoes the offending input value in its error messages, so a typo
    in ``.env`` would otherwise print an API key into the logs and the console.
    """
    try:
        errors = exc.errors()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        return ValueError("Invalid configuration; check backend/.env")
    masked = []
    for error in errors:
        location = error.get("loc") or ()
        name = str(location[0]) if location else "?"
        if name in _SENSITIVE_SETTING_NAMES:
            error["input"] = _mask_value(error.get("input"))
        masked.append(f"{'.'.join(str(part) for part in location)}: {error.get('msg')}")
    return ValueError("Invalid configuration: " + "; ".join(masked))


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
    #   The production frontend is always allowed; the loopback origins keep
    #   local development working without extra configuration. Loopback origins
    #   are dropped automatically outside development (see
    #   ``effective_cors_origins``), so a deployed backend is never served to a
    #   localhost page.
    PRODUCTION_FRONTEND_URL: str = PRODUCTION_FRONTEND_ORIGIN
    CORS_ORIGINS: str = (
        f"{PRODUCTION_FRONTEND_ORIGIN},http://localhost:3000,http://127.0.0.1:3000"
    )

    # Rate limiting (simple in-memory window limiter)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 60  # per window
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_AUTH_REQUESTS: int = 10  # stricter for /auth endpoints

    # AI provider: groq (the only supported production provider)
    AI_PROVIDER: str = "groq"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "qwen/qwen3.8-27b"  # verified in docs/AI_MODEL_SELECTION.md
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # ── Multi-provider fallback ─────────────────────────────────────────
    # Credentials are server-side only (never NEXT_PUBLIC_). Each provider is
    # independently optional: a missing key disables that fallback without
    # affecting the others or any unrelated feature.
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # Ordered list of providers to try: "groq,gemini,openai". A provider with no
    # usable credential is skipped rather than failing the request.
    AI_PROVIDER_PRIORITY: str = "groq,gemini,openai"
    # Automatic fallback to a provider that may incur cost requires explicit
    # opt-in; free capacity is always preferred.
    AI_ALLOW_PAID_FALLBACK: bool = False
    # Retries / backoff / circuit breaking for one provider attempt.
    AI_MAX_ATTEMPTS: int = 2
    AI_RETRY_BASE_SECONDS: float = 0.5
    AI_RETRY_MAX_SECONDS: float = 8.0
    AI_CIRCUIT_FAILURE_THRESHOLD: int = 3
    AI_CIRCUIT_COOLDOWN_SECONDS: float = 60.0
    # Per-request cost guard (0 disables the budget check).
    AI_DAILY_REQUEST_BUDGET: int = 0

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
    #   geoapify = Geoapify API (geocoding, places, routing) - default
    #   osm      = OpenStreetMap (Nominatim + Overpass + OSRM) - fallback, no billing
    #   google   = Google Maps Platform (requires Google Cloud billing)
    LOCATION_PROVIDER: str = "geoapify"
    GEOAPIFY_API_KEY: Optional[str] = None
    GEOAPIFY_BASE_URL: str = "https://api.geoapify.com/v1"
    GEOAPIFY_TIMEOUT_SECONDS: int = 15
    # OSM fallback settings (used when LOCATION_PROVIDER=osm)
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    OVERPASS_URL: str = "https://overpass-api.de/api/interpreter"
    OSRM_BASE_URL: str = "https://router.project-osrm.org"
    NOMINATIM_USER_AGENT: str = "RealEstateGPT/1.0"
    OSM_TIMEOUT_SECONDS: int = 15
    MAPS_PROVIDER: str = "none"  # google | none (optional, requires billing)
    GOOGLE_MAPS_SERVER_KEY: Optional[str] = None
    GOOGLE_MAPS_TIMEOUT_SECONDS: int = 10
    # Web search / property discovery layer
    #   Uses a legitimate Web Search API provider (no search-engine scraping).
    #   All secrets below are server-side; never prefix them with NEXT_PUBLIC_.
    WEB_DISCOVERY_ENABLED: bool = False
    WEB_SEARCH_PROVIDER: str = "brave"  # registered provider name, e.g. "brave", "searxng" or "tavily"
    BRAVE_SEARCH_API_KEY: Optional[str] = None
    # Required when WEB_SEARCH_PROVIDER=tavily. Server-side only: the frontend
    # must never see it (never a NEXT_PUBLIC_ variable).
    TAVILY_API_KEY: Optional[str] = None
    # "basic" = 1 API credit per request (free tier includes 1000 credits/month);
    # "advanced" = 2 credits and is not needed for property discovery.
    TAVILY_SEARCH_DEPTH: str = "basic"
    # Required when WEB_SEARCH_PROVIDER=searxng. There is deliberately NO
    # implicit localhost default: an unconfigured deployment reports
    # "not configured" instead of quietly depending on a developer machine.
    SEARXNG_BASE_URL: str = ""
    # Optional bearer token for a reverse-proxy-protected instance. When set,
    # every request sends "Authorization: Bearer <token>"; the production
    # SearXNG image (infra/searxng) rejects unauthenticated requests at its
    # Caddy edge unless the same token is configured there (SEARXNG_AUTH_TOKEN).
    SEARXNG_AUTH_TOKEN: str = ""
    WEB_SEARCH_COUNTRY: str = "IN"
    WEB_SEARCH_LANGUAGE: str = "en"
    WEB_SEARCH_MAX_QUERIES: int = 3
    WEB_SEARCH_MAX_RESULTS: int = 20
    WEB_SEARCH_CACHE_TTL_SECONDS: int = 300    # web_search_cache TTL
    WEB_DISCOVERY_TTL_HOURS: int = 72          # web_property_discoveries TTL
    WEB_SEARCH_TIMEOUT_SECONDS: int = 10
    WEB_SEARCH_MAX_RETRIES: int = 2            # retries beyond the first attempt (0-5)
    WEB_SEARCH_RPM: Optional[int] = None       # global provider requests/min (default 60)
    WEB_SEARCH_CONCURRENCY: int = 2            # max parallel provider requests
    WEB_DISCOVERY_OSM_ENRICH_LIMIT: int = 10   # max discoveries OSM/geocode-enriched
    WEB_SEARCH_ALLOWED_DOMAINS: str = ""       # comma-separated allowlist; empty = unrestricted
    PAGE_ENRICHMENT_ENABLED: bool = False      # optional page fetch (disabled by default)
    WEB_DISCOVERY_MIN_CONFIDENCE: float = 0.25  # candidates below this are dropped
    WEB_DISCOVERY_MAX_SOURCES: int = 4          # sources routed per search

    @property
    def web_search_allowed_domains(self) -> List[str]:
        """Normalized lower-case allowlist of domains, or [] when unrestricted."""
        return [d.strip().lower().lstrip(".") for d in self.WEB_SEARCH_ALLOWED_DOMAINS.split(",") if d.strip()]

    @property
    def web_search_configured(self) -> bool:
        """True when a real provider + credential is configured for web discovery.

        Outside development a loopback SearXNG URL never counts as configured:
        the deployed application must not depend on anyone's local machine.
        """
        provider = (self.WEB_SEARCH_PROVIDER or "").strip().lower()
        if provider == "brave":
            return bool(self.BRAVE_SEARCH_API_KEY)
        if provider == "tavily":
            return bool((self.TAVILY_API_KEY or "").strip())
        if provider == "searxng":
            url = (self.SEARXNG_BASE_URL or "").strip()
            if not url:
                return False
            if self.APP_ENV.strip().lower() != "development" and is_loopback_url(url):
                return False
            return True
        return False

    # Property data providers
    #   ""            = no provider configured (inventory stays empty; UI explains this)
    #   admin_import  = platform admin imports an authored record file (no scraping)
    PROPERTY_PROVIDER: str = ""  # registered adapter name, e.g. "admin_import"
    PROPERTY_PROVIDER_FILE: Optional[str] = "./data/property_provider.jsonl"
    PROVIDER_TIMEOUT_SECONDS: int = 30
    PROVIDER_RETRIES: int = 2
    PROVIDER_RETRY_BACKOFF_SECONDS: float = 2.0
    PROVIDER_MIN_INTERVAL_SECONDS: float = 0.5  # provider rate limiting floor
    INGESTION_BATCH_SIZE: int = 50
    INGESTION_MAX_PAGES: int = 20

    # Background jobs / workers
    REDIS_URL: Optional[str] = None
    # Vercel Cron sends this value as ``Authorization: Bearer <CRON_SECRET>``.
    # It is deliberately distinct from WORKER_RUN_SECRET, which is used by an
    # external scheduler calling an individual POST worker endpoint.
    CRON_SECRET: Optional[str] = None
    WORKER_RUN_SECRET: str = "change-this-worker-secret-in-production"
    WORKER_LOCK_TTL_SECONDS: int = 900
    # Listing freshness lifecycle
    LISTING_STALE_AFTER_HOURS: int = 72   # active -> stale after no provider sightings
    LISTING_EXPIRE_AFTER_DAYS: int = 21   # stale -> expired after long absence

    @property
    def cors_origins_list(self) -> List[str]:
        """The configured CORS allowlist exactly as supplied (never mutated)."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def effective_cors_origins(self) -> List[str]:
        """The CORS allowlist actually applied at runtime.

        Outside development every loopback origin is removed, so a deployed
        backend can never be driven by a page served from someone's laptop
        while development stays friction-free. A wildcard is passed through
        untouched, and the configuration is never silently reduced to nothing:
        if filtering would empty the list the original value is kept and an
        error is logged instead (a broken allowlist must be loud, not silent).
        """
        origins = self.cors_origins_list
        if self.APP_ENV.strip().lower() == "development":
            return origins
        kept = [o for o in origins if o == "*" or not is_loopback_url(o)]
        dropped = [o for o in origins if o not in kept]
        if not kept:
            logger.error(
                "CORS_ORIGINS contains only loopback origins; keeping them so the "
                "API stays reachable. Set CORS_ORIGINS to the deployed frontend URL."
            )
            return origins
        if dropped:
            logger.warning(
                "Ignoring loopback CORS origins outside development: %s", ", ".join(dropped)
            )
        return kept

    def configuration_warnings(self) -> list[str]:
        """Non-fatal deployment problems, logged once at startup.

        These never stop the application: a missing optional integration must
        degrade to an honest "not configured" state, not a crash loop.
        """
        warnings: list[str] = []
        env = self.APP_ENV.strip().lower()
        if env == "development":
            return warnings

        provider = (self.WEB_SEARCH_PROVIDER or "").strip().lower()
        if self.WEB_DISCOVERY_ENABLED:
            if provider == "searxng":
                if not self.SEARXNG_BASE_URL:
                    warnings.append(
                        "WEB_DISCOVERY_ENABLED=true with WEB_SEARCH_PROVIDER=searxng but "
                        "SEARXNG_BASE_URL is empty; web discovery will report "
                        "WEB_SEARCH_NOT_CONFIGURED."
                    )
                elif is_loopback_url(self.SEARXNG_BASE_URL):
                    warnings.append(
                        "SEARXNG_BASE_URL points at loopback; a deployed backend must use a "
                        "publicly reachable SearXNG host. Web discovery will report "
                        "WEB_SEARCH_NOT_CONFIGURED."
                    )
                elif not self.SEARXNG_BASE_URL.strip().lower().startswith("https://"):
                    warnings.append("SEARXNG_BASE_URL should use https outside development.")
            elif provider == "brave":
                if not self.BRAVE_SEARCH_API_KEY:
                    warnings.append(
                        "WEB_DISCOVERY_ENABLED=true with WEB_SEARCH_PROVIDER=brave but "
                        "BRAVE_SEARCH_API_KEY is empty."
                    )
            elif provider == "tavily":
                if not (self.TAVILY_API_KEY or "").strip():
                    warnings.append(
                        "WEB_DISCOVERY_ENABLED=true with WEB_SEARCH_PROVIDER=tavily but "
                        "TAVILY_API_KEY is empty; web discovery will report "
                        "WEB_SEARCH_NOT_CONFIGURED."
                    )
            else:
                warnings.append(
                    f"WEB_SEARCH_PROVIDER='{self.WEB_SEARCH_PROVIDER}' is not registered; "
                    "expected 'brave', 'searxng' or 'tavily'."
                )

        if (self.WORKER_RUN_SECRET or "").strip() in {
            "", "change-this-worker-secret-in-production",
        }:
            warnings.append(
                "WORKER_RUN_SECRET is missing or still the placeholder value; scheduled "
                "workers cannot be triggered securely."
            )

        if not (self.CRON_SECRET or "").strip():
            warnings.append(
                "CRON_SECRET is not configured; Vercel Cron endpoints will reject requests."
            )

        if not any(o.startswith("https://") for o in self.cors_origins_list):
            warnings.append("CORS_ORIGINS has no https origin; the deployed frontend will be blocked.")

        return warnings

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
        """True when at least one real LLM provider credential is present."""
        return bool(
            (self.GROQ_API_KEY or "").strip()
            or (self.GEMINI_API_KEY or "").strip()
            or (self.OPENAI_API_KEY or "").strip()
        )

    @property
    def ai_provider_priority(self) -> List[str]:
        """The configured provider order, de-duplicated."""
        seen: List[str] = []
        for name in (self.AI_PROVIDER_PRIORITY or "").split(","):
            cleaned = name.strip().lower()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen

    @property
    def ai_paid_fallback_allowed(self) -> bool:
        """Automatic fallback to a cost-incurring provider requires opt-in."""
        return bool(self.AI_ALLOW_PAID_FALLBACK)

    def validate_runtime(self) -> list[str]:
        """Fail-fast configuration checks. Returns a list of problems.

        Called once at application startup. Development environments keep the
        friendly defaults documented in ``.env.example``; any other environment
        must not run with placeholder secrets or a missing database.
        """
        problems: list[str] = []
        env = self.APP_ENV.strip().lower()
        if not self.MONGODB_URI:
            problems.append("MONGODB_URI is not configured.")
        if env != "development":
            if not self.SECRET_KEY or len(self.SECRET_KEY) < 16 or self.SECRET_KEY in {
                "change-this-in-production", "change-this-to-a-random-secret-key-in-production",
            }:
                problems.append("SECRET_KEY must be a long random value outside development.")
            if not self.ai_configured:
                problems.append(
                    "At least one AI provider credential is required outside development "
                    "(GROQ_API_KEY, GEMINI_API_KEY or OPENAI_API_KEY)."
                )
            if not self.CRON_SECRET or len(self.CRON_SECRET) < 16:
                problems.append("CRON_SECRET must be a long random value outside development.")
            provider = self.LOCATION_PROVIDER.strip().lower()
            if provider not in {"geoapify", "osm", "google"}:
                problems.append("LOCATION_PROVIDER must be a configured provider (geoapify, osm, or google).")
            elif not self._location_provider_configured(provider, self):
                if provider == "geoapify":
                    problems.append("LOCATION_PROVIDER=geoapify requires GEOAPIFY_API_KEY.")
                elif provider == "google":
                    problems.append("LOCATION_PROVIDER=google requires GOOGLE_MAPS_SERVER_KEY.")
            # Web discovery misconfiguration is NOT fatal: it is an optional
            # integration that must degrade to an honest WEB_SEARCH_NOT_CONFIGURED
            # state (see configuration_warnings). Failing startup here would take
            # down every endpoint — auth, health, inventory — because one optional
            # provider is unset.
        return problems

    @staticmethod
    def _location_provider_configured(provider: str, settings_obj: "Settings") -> bool:
        provider = provider.strip().lower()
        if provider == "geoapify":
            return bool(settings_obj.GEOAPIFY_API_KEY)
        if provider == "osm":
            return True  # OSM uses public services
        if provider == "google":
            return bool(settings_obj.GOOGLE_MAPS_SERVER_KEY)
        return False

    def __init__(self, **values):
        try:
            super().__init__(**values)
        except Exception as exc:  # ValidationError and friends
            # Never let a credential reach a traceback, a log line or a response.
            raise _safe_settings_validation_error(exc) from None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


def _load_settings() -> "Settings":
    try:
        return Settings()
    except ValueError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise _safe_settings_validation_error(exc) from None


settings = _load_settings()
