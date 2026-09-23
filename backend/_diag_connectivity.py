"""Diagnostic: verify MongoDB and Groq connectivity without printing secrets."""
from __future__ import annotations

import sys
import time

from app.core.config import settings


def check_mongodb() -> bool:
    from app.core import database
    started = time.perf_counter()
    try:
        ok = database.ping()
    except Exception as exc:  # noqa: BLE001 - diagnostic
        print(f"MONGODB: FAIL ({type(exc).__name__}: {exc})")
        return False
    elapsed = (time.perf_counter() - started) * 1000
    if ok:
        db = database.get_database()
        names = db.list_collection_names()
        print(f"MONGODB: OK (ping {elapsed:.0f} ms, database={settings.MONGODB_DATABASE}, "
              f"collections={len(names)})")
        targets = {
            "web_property_discoveries", "web_search_cache", "source_health",
            "discovery_runs", "saved_discoveries",
        }
        present = sorted(targets.intersection(names))
        print(f"MONGODB discovery collections present: {present}")
        return True
    print(f"MONGODB: FAIL (ping returned False after {elapsed:.0f} ms)")
    return False


def check_groq() -> bool:
    import httpx
    key = settings.GROQ_API_KEY
    if not key:
        print("GROQ: FAIL (GROQ_API_KEY not set)")
        return False
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                f"{settings.GROQ_BASE_URL}/models",
                headers={"Authorization": f"Bearer {key}"},
            )
        if resp.status_code == 200:
            models = resp.json().get("data", [])
            ids = [m.get("id", "") for m in models]
            configured = settings.GROQ_MODEL
            available = configured in ids
            print(f"GROQ: OK ({len(models)} models listed; configured model "
                  f"'{configured}' {'available' if available else 'NOT in list'})")
            return True
        print(f"GROQ: FAIL (HTTP {resp.status_code})")
        return False
    except Exception as exc:  # noqa: BLE001 - diagnostic
        print(f"GROQ: FAIL ({type(exc).__name__}: {exc})")
        return False


def check_osm() -> bool:
    import httpx
    try:
        with httpx.Client(timeout=settings.OSM_TIMEOUT_SECONDS) as client:
            resp = client.get(
                f"{settings.NOMINATIM_BASE_URL}/search",
                params={"q": "Hyderabad", "format": "json", "limit": 1},
                headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
            )
        ok = resp.status_code == 200 and bool(resp.json())
        print(f"OSM/NOMINATIM: {'OK' if ok else f'FAIL (HTTP {resp.status_code})'}")
        return ok
    except Exception as exc:  # noqa: BLE001 - diagnostic
        print(f"OSM/NOMINATIM: FAIL ({type(exc).__name__}: {exc})")
        return False


def check_osrm() -> bool:
    import httpx
    try:
        with httpx.Client(timeout=settings.OSM_TIMEOUT_SECONDS) as client:
            resp = client.get(
                f"{settings.OSRM_BASE_URL}/route/v1/driving/78.4867,17.3850;78.4353,17.2403",
                params={"overview": "false"},
            )
        ok = resp.status_code == 200 and resp.json().get("code") == "Ok"
        print(f"OSRM: {'OK' if ok else f'FAIL (HTTP {resp.status_code})'}")
        return ok
    except Exception as exc:  # noqa: BLE001 - diagnostic
        print(f"OSRM: FAIL ({type(exc).__name__}: {exc})")
        return False


if __name__ == "__main__":
    print(f"APP_ENV={settings.APP_ENV}  WEB_SEARCH_PROVIDER={settings.WEB_SEARCH_PROVIDER}  "
          f"web_search_configured={settings.web_search_configured}")
    results = {
        "mongodb": check_mongodb(),
        "groq": check_groq(),
        "osm": check_osm(),
        "osrm": check_osrm(),
    }
    failed = [name for name, ok in results.items() if not ok]
    print("SUMMARY:", "ALL OK" if not failed else f"FAILED: {', '.join(failed)}")
    sys.exit(0 if not failed else 1)
