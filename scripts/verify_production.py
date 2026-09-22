#!/usr/bin/env python3
"""RealEstateGPT production verification.

Probes the ACTUAL deployed application (frontend + API) and records the result
of every check: HTTP method, URL, status code and latency. Nothing here is
mocked, and nothing is invented: a failure is reported as a failure.

Usage (from the repository root)::

    python scripts/verify_production.py
    python scripts/verify_production.py --report docs/production_verification_report.json
    python scripts/verify_production.py --base-url https://example.com --skip-auth

Requirements: ``httpx`` (already a backend dependency).

Exit code is 0 only when every mandatory check passed. Optional integrations
(web discovery, AI) that are legitimately "not configured" are reported as
WARN/SKIP rather than swallowed or faked.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = os.environ.get(
    "PRODUCTION_BASE_URL", "https://realestate-gpt-inky.vercel.app"
)
API_PREFIX = "/api/backend/api/v1"
TIMEOUT = 45.0

FRONTEND_PAGES = [
    ("/", "Landing page"),
    ("/search", "Search"),
    ("/auth/login", "Login"),
    ("/auth/register", "Register"),
    ("/assistant", "AI assistant"),
    ("/saved", "Saved properties"),
    ("/compare", "Compare"),
    ("/admin", "Admin"),
    ("/robots.txt", "robots.txt"),
    ("/sitemap.xml", "sitemap.xml"),
]


@dataclass
class Check:
    name: str
    method: str
    url: str
    status: int
    latency_ms: float
    outcome: str  # PASS | FAIL | WARN | SKIP
    detail: str = ""
    auth: str = "public"
    extra: dict[str, Any] = field(default_factory=dict)


class Report:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.checks: list[Check] = []
        self.started_at = datetime.now(timezone.utc)
        self.notes: list[str] = []

    def add(self, check: Check) -> Check:
        self.checks.append(check)
        marker = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}[check.outcome]
        print(
            f"  [{marker}] {check.method:<6} {check.url} -> {check.status} "
            f"({check.latency_ms:.0f}ms) {check.detail}".rstrip()
        )
        return check

    def counts(self) -> dict[str, int]:
        out = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
        for check in self.checks:
            out[check.outcome] = out.get(check.outcome, 0) + 1
        return out

    def to_dict(self) -> dict[str, Any]:
        latencies = [c.latency_ms for c in self.checks if c.outcome != "SKIP"]
        return {
            "base_url": self.base_url,
            "started_at": self.started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "summary": self.counts(),
            "latency_ms": {
                "count": len(latencies),
                "min": round(min(latencies), 1) if latencies else None,
                "median": round(statistics.median(latencies), 1) if latencies else None,
                "max": round(max(latencies), 1) if latencies else None,
            },
            "notes": self.notes,
            "checks": [
                {
                    "name": c.name,
                    "method": c.method,
                    "url": c.url,
                    "status": c.status,
                    "latency_ms": round(c.latency_ms, 1),
                    "outcome": c.outcome,
                    "auth": c.auth,
                    "detail": c.detail,
                    "extra": c.extra,
                }
                for c in self.checks
            ],
        }



def call(
    client: httpx.Client,
    report: Report,
    name: str,
    method: str,
    url: str,
    *,
    expected: tuple[int, ...] = (200,),
    auth: str = "public",
    detail: str = "",
    json_body: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    soft: bool = False,
    warn_if: tuple[int, ...] = (),
) -> Optional[httpx.Response]:
    """Perform one request, record it, and return the response.

    ``soft=True`` turns any unexpected status into WARN. ``warn_if`` lists
    specific statuses that are external/quota conditions rather than defects
    (e.g. a provider rate limit) and should be reported as WARN without hiding
    the code.
    """
    started = time.perf_counter()
    try:
        response = client.request(
            method, url, json=json_body, headers=headers, follow_redirects=False
        )
    except httpx.HTTPError as exc:
        latency = (time.perf_counter() - started) * 1000
        report.add(Check(
            name=name, method=method, url=url, status=0, latency_ms=latency,
            outcome="WARN" if soft else "FAIL", auth=auth,
            detail=f"transport error: {type(exc).__name__}: {exc}"[:240],
        ))
        return None

    latency = (time.perf_counter() - started) * 1000
    ok = response.status_code in expected
    if ok:
        outcome = "PASS"
    elif response.status_code in warn_if:
        outcome = "WARN"
    else:
        outcome = "WARN" if soft else "FAIL"

    try:
        error_code = (response.json() or {}).get("detail", {})
        error_code = error_code.get("code") if isinstance(error_code, dict) else None
    except ValueError:
        error_code = None

    if ok:
        detail_text = detail
    elif response.status_code in warn_if:
        detail_text = f"HTTP {response.status_code}{f' {error_code}' if error_code else ''} (external/quota condition)"
    else:
        detail_text = f"expected {expected} -> got {response.status_code}"

    report.add(Check(
        name=name, method=method, url=url, status=response.status_code,
        latency_ms=latency, outcome=outcome, auth=auth, detail=detail_text,
        extra={"error_code": error_code} if error_code else {},
    ))
    return response


def body_json(response: Optional[httpx.Response]) -> Any:
    if response is None:
        return None
    try:
        return response.json()
    except ValueError:
        return None


# ─── Frontend ───────────────────────────────────────────────────────────────

def verify_frontend(client: httpx.Client, report: Report) -> None:
    print("\nFrontend (real production pages)")
    for path, label in FRONTEND_PAGES:
        response = call(
            client, report, f"frontend {label}", "GET", report.base_url + path,
            expected=(200,), detail=label,
        )
        if response is not None and response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if path.endswith((".txt", ".xml")):
                report.checks[-1].extra["content_type"] = content_type
            elif "text/html" not in content_type:
                report.checks[-1].outcome = "WARN"
                report.checks[-1].detail = f"unexpected content-type {content_type}"

    # SEO surface: canonical/OG must not point at a placeholder domain.
    response = call(client, report, "landing metadata", "GET", report.base_url + "/")
    if response is not None:
        html = response.text
        placeholder = "realestategpt.example.com" in html
        report.checks[-1].extra["placeholder_domain_present"] = placeholder
        if placeholder:
            report.checks[-1].outcome = "FAIL"
            report.checks[-1].detail = "canonical/OG points at realestategpt.example.com"
        else:
            report.checks[-1].detail = "no placeholder domain in canonical/OG"


# ─── API ────────────────────────────────────────────────────────────────────

def verify_api_health(client: httpx.Client, report: Report, api: str) -> dict[str, Any]:
    print("\nAPI health / configuration")
    facts: dict[str, Any] = {}

    response = call(client, report, "health", "GET", f"{api}/health")
    payload = body_json(response)
    if isinstance(payload, dict):
        facts["version"] = payload.get("version")
        facts["status"] = payload.get("status")
        report.checks[-1].extra.update(payload)
        report.checks[-1].detail = (
            f"status={payload.get('status')} version={payload.get('version')}"
        )

    response = call(client, report, "health db (MongoDB Atlas)", "GET", f"{api}/health/db")
    payload = body_json(response)
    if isinstance(payload, dict):
        facts["database"] = payload.get("status")
        report.checks[-1].detail = json.dumps(payload)[:200]
        if payload.get("status") != "healthy":
            report.checks[-1].outcome = "FAIL"

    response = call(client, report, "health ai (Groq)", "GET", f"{api}/health/ai")
    payload = body_json(response)
    if isinstance(payload, dict):
        facts["ai_configured"] = bool(payload.get("configured"))
        facts["ai_provider"] = payload.get("provider")
        report.checks[-1].detail = (
            f"provider={payload.get('provider')} configured={payload.get('configured')}"
        )
        if not payload.get("configured"):
            report.checks[-1].outcome = "WARN"

    response = call(client, report, "health location (OSM)", "GET", f"{api}/health/location")
    payload = body_json(response)
    if isinstance(payload, dict):
        facts["location_provider"] = payload.get("provider")
        report.checks[-1].detail = f"provider={payload.get('provider')}"

    response = call(
        client, report, "health web-search", "GET", f"{api}/health/web-search",
        expected=(200,), soft=True,
    )
    payload = body_json(response)
    if isinstance(payload, dict):
        facts["web_search"] = {
            "configured": payload.get("configured"),
            "enabled": payload.get("enabled"),
            "status": payload.get("status"),
            "provider": payload.get("provider"),
        }
        report.checks[-1].detail = (
            f"provider={payload.get('provider')} configured={payload.get('configured')} "
            f"enabled={payload.get('enabled')} status={payload.get('status')}"
        )
        if not payload.get("configured"):
            report.checks[-1].outcome = "WARN"

    response = call(client, report, "workers status", "GET", f"{api}/workers/status")
    payload = body_json(response)
    if isinstance(payload, dict):
        facts["property_provider"] = payload.get("property_provider")
        facts["property_provider_configured"] = payload.get(
            "property_provider_configured"
        )
        report.checks[-1].detail = (
            f"provider={payload.get('property_provider')!r} "
            f"configured={payload.get('property_provider_configured')}"
        )

    # Worker endpoints must reject unauthenticated runs.
    call(
        client, report, "workers run without secret (must be 401)", "POST",
        f"{api}/workers/run/stale_listing_worker", expected=(401,), auth="none",
    )
    call(
        client, report, "workers runs list without admin (must be 403)", "GET",
        f"{api}/workers/runs?worker_name=stale_listing_worker", expected=(403,), auth="none",
    )
    return facts


# ─── Authentication + authorization ────────────────────────────────────────

def verify_auth(client: httpx.Client, report: Report, api: str) -> Optional[str]:
    print("\nAuthentication / authorization")
    email = f"prod-verify-{uuid.uuid4().hex[:12]}@example.com"
    password = "ProdVerify1x"
    token: Optional[str] = None

    # Validation must reject a weak payload before any write happens.
    call(
        client, report, "register weak password (must be 422)", "POST",
        f"{api}/auth/register", expected=(422,),
        json_body={"email": "not-an-email", "full_name": "x", "password": "short"},
    )

    response = call(
        client, report, "register", "POST", f"{api}/auth/register",
        expected=(201, 409), auth="none",
        json_body={"email": email, "full_name": "Production Verify", "password": password},
        detail=f"account={email}",
    )
    if response is None or response.status_code != 201:
        return None
    token = (body_json(response) or {}).get("access_token")
    report.checks[-1].extra["email"] = email

    response = call(
        client, report, "register duplicate (must be 409)", "POST", f"{api}/auth/register",
        expected=(409,), auth="none",
        json_body={"email": email, "full_name": "Production Verify", "password": password},
    )

    call(
        client, report, "login wrong password (must be 401)", "POST", f"{api}/auth/login",
        expected=(401,), auth="none",
        json_body={"email": email, "password": "WrongPassword1"},
    )

    response = call(
        client, report, "login", "POST", f"{api}/auth/login",
        expected=(200,), auth="none",
        json_body={"email": email, "password": password},
    )
    if response is None or response.status_code != 200:
        return None
    payload = body_json(response) or {}
    token = payload.get("access_token") or token
    report.checks[-1].detail = f"role={(payload.get('user') or {}).get('role')}"

    # Protected endpoints must reject missing/invalid/expired-style credentials.
    call(client, report, "me without token (must be 401)", "GET", f"{api}/auth/me", expected=(401,), auth="none")
    call(
        client, report, "me with forged token (must be 401)", "GET", f"{api}/auth/me",
        expected=(401,), auth="invalid",
        headers={"Authorization": "Bearer not.a.real.token"},
    )

    if token:
        call(
            client, report, "me with valid token", "GET", f"{api}/auth/me",
            expected=(200,), auth="bearer",
            headers={"Authorization": f"Bearer {token}"},
        )

    # A normal user must not reach admin surfaces.
    admin_headers = {"Authorization": f"Bearer {token}"} if token else None
    call(
        client, report, "admin stats as normal user (must be 403)", "GET",
        f"{api}/admin/stats", expected=(403,), auth="bearer", headers=admin_headers,
    )
    call(
        client, report, "admin users as normal user (must be 403)", "GET",
        f"{api}/admin/users", expected=(403,), auth="bearer", headers=admin_headers,
    )
    call(
        client, report, "create property as normal user (must be 403)", "POST",
        f"{api}/properties", expected=(403,), auth="bearer", headers=admin_headers,
        json_body={
            "title": "Unauthorized listing attempt", "price": 1000,
            "property_type": "apartment", "city": "Hyderabad",
        },
    )
    return token


# ─── Functional surface ────────────────────────────────────────────────────

def verify_functional(
    client: httpx.Client, report: Report, api: str, token: Optional[str]
) -> None:
    print("\nSearch / property / finance / AI / discovery")
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Natural-language parsing is deterministic and must never invent filters.
    response = call(
        client, report, "natural language parse", "GET",
        f"{api}/search/parse?q=2BHK%20under%2030k%20rent%20in%20Hyderabad",
    )
    payload = body_json(response)
    if isinstance(payload, dict):
        report.checks[-1].detail = (
            f"city={payload.get('city')} bedrooms={payload.get('bedrooms')} "
            f"listing_type={payload.get('listing_type')} max_price={payload.get('max_price')}"
        )

    call(client, report, "dynamic result sections", "GET", f"{api}/search/sections?q=apartment")
    call(
        client, report, "property list", "GET",
        f"{api}/properties?page=1&page_size=5&sort_by=created_at&sort_order=desc",
    )
    call(client, report, "featured properties", "GET", f"{api}/properties/featured?limit=6")
    call(
        client, report, "property not found (must be 404)", "GET",
        f"{api}/properties/999999999", expected=(404,),
    )
    call(
        client, report, "property validation (must be 422)", "GET",
        f"{api}/properties?min_price=abc", expected=(422,),
    )

    # Near-me: bounds are validated; valid coordinates return an honest result set.
    call(
        client, report, "near-me", "POST", f"{api}/search/near-me",
        json_body={"latitude": 17.4435, "longitude": 78.3772, "radius_km": 5},
    )
    call(
        client, report, "near-me out of range (must be 422)", "POST", f"{api}/search/near-me",
        expected=(422,),
        json_body={"latitude": 999, "longitude": 78.3772, "radius_km": 5},
    )

    # Unified search: verified inventory and web discovery are separate lists.
    response = call(
        client, report, "unified search", "POST", f"{api}/search",
        json_body={"query": "3BHK under 90 lakhs near metro in Hyderabad", "limit": 6},
    )
    payload = body_json(response)
    if isinstance(payload, dict):
        metadata = payload.get("metadata") or {}
        report.checks[-1].detail = (
            f"verified={payload.get('verified_total')} web={payload.get('web_total')} "
            f"provider_status={metadata.get('provider_status')} "
            f"sections={len(payload.get('sections') or [])}"
        )
        report.checks[-1].extra["metadata"] = metadata
        # The two result sets must be present and distinguishable.
        if payload.get("verified_properties") is None or payload.get("web_discoveries") is None:
            report.checks[-1].outcome = "FAIL"
            report.checks[-1].detail = "verified and web result lists are not separated"

    # Location intelligence (OSM/Nominatim) — real external dependency.
    call(
        client, report, "geocode (Nominatim)", "POST", f"{api}/locations/geocode",
        json_body={"address": "Gachibowli, Hyderabad"},
        warn_if=(429, 503),  # public OSM infrastructure rate limits / outages
    )
    call(client, report, "location provider status", "GET", f"{api}/locations/status")

    # Finance calculators are deterministic: verify the maths, not just 200 OK.
    response = call(
        client, report, "finance EMI", "POST", f"{api}/finance/emi",
        json_body={"principal": 5000000, "annual_interest_rate": 8.5, "tenure_years": 20},
    )
    payload = body_json(response)
    if isinstance(payload, dict):
        emi = payload.get("monthly_emi") or payload.get("emi")
        # Independently recompute the standard EMI so a wrong number is caught,
        # not just a missing one.
        principal, annual_rate, years = 5_000_000.0, 8.5, 20.0
        monthly_rate = annual_rate / 12 / 100
        months = years * 12
        growth = (1 + monthly_rate) ** months
        expected = principal * monthly_rate * growth / (growth - 1)
        report.checks[-1].detail = f"monthly_emi={emi} expected={expected:.2f}"
        report.checks[-1].extra["monthly_emi"] = emi
        report.checks[-1].extra["expected_monthly_emi"] = round(expected, 2)
        if not isinstance(emi, (int, float)) or abs(float(emi) - expected) / expected > 0.005:
            report.checks[-1].outcome = "FAIL"
            report.checks[-1].detail = f"monthly_emi={emi} does not match expected {expected:.2f}"

    call(
        client, report, "finance affordability", "POST", f"{api}/finance/affordability",
        json_body={"monthly_income": 150000, "existing_obligations": 20000, "down_payment": 1000000},
    )
    call(
        client, report, "finance rental yield", "POST", f"{api}/finance/rental-yield",
        json_body={"property_price": 7500000, "monthly_rent": 35000},
    )

    # AI gateway (Groq). Only meaningful when configured.
    call(
        client, report, "ai search", "POST", f"{api}/ai/search", soft=True, headers=auth_headers,
        json_body={"query": "affordable apartments near Gachibowli", "limit": 5},
    )
    if token:
        response = call(
            client, report, "ai assistant (Groq tool-calling)", "POST", f"{api}/ai/assistant",
            auth="bearer", headers=auth_headers,
            # A shared Groq key can legitimately be rate limited; that is an
            # external quota condition, reported as WARN with the typed code.
            warn_if=(429, 504),
            json_body={"message": "What can you tell me about the current property catalogue?"},
        )
        payload = body_json(response)
        if isinstance(payload, dict):
            text = str(payload.get("message") or payload.get("response") or "")
            report.checks[-1].detail = (
                f"provider={payload.get('provider')} tools={len(payload.get('tool_calls') or [])} "
                f"chars={len(text)}"
            )
    else:
        report.add(Check(
            name="ai assistant (Groq tool-calling)", method="POST", url=f"{api}/ai/assistant",
            status=0, latency_ms=0.0, outcome="SKIP", auth="bearer",
            detail="no auth token available",
        ))


# ─── CLI ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the deployed RealEstateGPT application.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Production origin")
    parser.add_argument("--report", default="", help="Write the JSON report to this path")
    parser.add_argument("--skip-auth", action="store_true", help="Skip account creation checks")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    api = base + API_PREFIX
    report = Report(base)
    report.notes.append(
        "Checks are performed against the real deployment. Optional integrations that "
        "are not configured are reported as WARN, never as PASS and never as fake data."
    )

    print(f"RealEstateGPT production verification -> {base}")
    print(f"API base: {api}")

    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "RealEstateGPT-Verifier/1.0"}) as client:
        verify_frontend(client, report)
        facts = verify_api_health(client, report, api)
        report.notes.append(f"health snapshot: {json.dumps(facts, default=str)}")
        token = None
        if not args.skip_auth:
            token = verify_auth(client, report, api)
        else:
            report.notes.append("auth checks skipped (--skip-auth)")
        verify_functional(client, report, api, token)

    counts = report.counts()
    print("\n=== Summary ===")
    print(f"  base_url : {base}")
    print(f"  version  : {facts.get('version')}")
    print(f"  PASS {counts['PASS']}  WARN {counts['WARN']}  SKIP {counts['SKIP']}  FAIL {counts['FAIL']}")
    latency = report.to_dict()["latency_ms"]
    print(f"  latency  : median {latency['median']}ms, max {latency['max']}ms")

    if counts["FAIL"]:
        print("\nFailures:")
        for check in report.checks:
            if check.outcome == "FAIL":
                print(f"  - {check.method} {check.url} -> {check.status} ({check.detail})")

    if args.report:
        path = os.path.abspath(args.report)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2, default=str)
        print(f"\nReport written to {path}")

    # WARN is acceptable (an integration may legitimately be unconfigured);
    # FAIL is not.
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())




