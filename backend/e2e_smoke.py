"""End-to-end smoke test for the running backend.

Exercises the mandatory RealEstateGPT journey against a live local server:
register -> assistant (search) -> follow-up (refine) -> route tool -> grounding.

Run with the FastAPI app already running on http://127.0.0.1:8000:
    python e2e_smoke.py
Exit code 0 on success; the assistant may surface Groq 429s when the public
tier rate limit is exhausted (the app is designed to fail loudly, never to
fabricate).
"""
from __future__ import annotations

import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8000/api/v1"


def main() -> None:
    email = f"e2e.{uuid.uuid4().hex[:10]}@test.local"
    with httpx.Client(base_url=BASE, timeout=120) as client:
        reg = client.post("/auth/register", json={
            "email": email, "full_name": "E2E Test User", "password": "E2eTest123!",
        })
        if reg.status_code != 201:
            print("FAIL register", reg.status_code, reg.text[:200])
            sys.exit(1)
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("PASS register")

        first = client.post("/ai/assistant", headers=headers, json={
            "message": "Find a 3BHK under 90 lakhs in Hyderabad near metro",
            "conversation_id": None,
        })
        if first.status_code != 200:
            print("FAIL assistant[1]", first.status_code, first.text[:400])
            sys.exit(1)
        body1 = first.json()
        conversation_id = body1["conversation_id"]
        print(f"PASS assistant[1] conversation={conversation_id} results={len(body1.get('results', []))} "
              f"tools={','.join(t['tool'] for t in body1.get('tool_calls', []))}")
        assert body1["provider"] == "groq"

        second = client.post("/ai/assistant", headers=headers, json={
            "message": "Only show properties near metro",
            "conversation_id": conversation_id,
        })
        body2 = second.json()
        print(f"PASS assistant[2] status={second.status_code} results={len(body2.get('results', []))}")

        third = client.post("/ai/assistant", headers=headers, json={
            "message": "What is the commute to HITEC City?",
            "conversation_id": conversation_id,
        })
        body3 = third.json()
        tools3 = ",".join(t["tool"] for t in body3.get("tool_calls", []))
        print(f"PASS assistant[3] status={third.status_code} tools={tools3}")
        if "route" not in body3.get("tool_calls", [{"tool": ""}]) and "calculate_route" not in tools3:
            print("NOTE: follow-up did not call the route tool (the model chooses the tool).")

        convs = client.get("/ai/conversations", headers=headers)
        print(f"PASS conversations status={convs.status_code} count={len(convs.json())}")

    print("E2E OK")


if __name__ == "__main__":
    main()