"""Overpass mirror fallback tests.

The public Overpass instances return 429/502/503/504 under load. A
single-mirror implementation surfaces those as a 503 in the browser for a city
that is perfectly well mapped, so the provider asks every mirror at once and
uses the first healthy answer.
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.providers.location import (
    LocationProviderInvalidRequest,
    LocationProviderUnavailable,
)
from app.providers.openstreetmap.provider import (
    OpenStreetMapLocationProvider,
    _overpass_endpoints,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class _BrokenJsonResponse:
    """A 200 whose body cannot be parsed as JSON."""

    status_code = 200

    def json(self):
        raise ValueError("not json")


class _RecordingClient:
    """Scripts one outcome queue per URL; records every URL it was pointed at.

    Mirror attempts run in parallel threads, so outcomes are keyed by URL
    instead of popped from a shared list (a shared queue would make the test
    depend on thread scheduling).
    """

    def __init__(self, script: dict[str, list[object]]) -> None:
        self.script = {url: list(outcomes) for url, outcomes in script.items()}
        self.calls: list[str] = []
        self.script_sent: list[dict] = []
        self._lock = __import__("threading").Lock()

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def post(self, url, data=None, **kwargs):
        with self._lock:
            self.calls.append(url)
            self.script_sent.append(dict(data) if isinstance(data, dict) else {"data": data})
            queue = self.script.get(url)
            outcome = queue.pop(0) if queue else _FakeResponse(200, {"elements": []})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


_ENDPOINTS = ["https://a.example/api/interpreter", "https://b.example/api/interpreter"]


def _run(provider, client, endpoints=_ENDPOINTS, total_budget: float = 20.0):
    """Patch the mirror list, the HTTP client and the inter-round sleep."""
    return (
        patch(
            "app.providers.openstreetmap.provider._overpass_endpoints",
            return_value=list(endpoints),
        ),
        patch.object(
            OpenStreetMapLocationProvider, "_client", staticmethod(lambda **_kw: client)
        ),
        patch("time.sleep", lambda *_a: None),
    )


def test_overpass_endpoints_include_the_configured_url_first():
    with patch("app.providers.openstreetmap.provider.settings") as settings:
        settings.OVERPASS_URL = "https://overpass-api.de/api/interpreter"
        endpoints = _overpass_endpoints()
    assert endpoints[0] == "https://overpass-api.de/api/interpreter"
    assert len(endpoints) > 1
    assert len(set(endpoints)) == len(endpoints), "mirrors must be deduplicated"


def test_overpass_uses_a_healthy_mirror_when_another_is_throttled():
    """A 503 on one mirror must not sink the request: another mirror answers."""
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [_FakeResponse(503)],
        "https://b.example/api/interpreter": [_FakeResponse(200, {"elements": [{"id": 1}]})],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        elements = provider._overpass_query("[out:json];();out;")

    assert elements == [{"id": 1}]
    assert sorted(client.calls) == sorted(_ENDPOINTS), "every mirror is asked in parallel"


def test_overpass_falls_back_on_rate_limit():
    """A 429 on the primary must not be answered by a fallback's empty body.

    Only the configured endpoint (or a unanimous round) may report "nothing is
    mapped here", so an unavailable primary is surfaced as an error rather
    than as a fake empty result.
    """
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [_FakeResponse(429), _FakeResponse(429)],
        "https://b.example/api/interpreter": [_FakeResponse(200, {"elements": []})],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        with pytest.raises(LocationProviderUnavailable):
            provider._overpass_query("[out:json];();out;")

    assert len(client.calls) == 4, "both mirrors are asked in both rounds"


def test_overpass_trusts_the_configured_endpoint_empty_answer():
    """The primary's 'nothing mapped here' is authoritative over a failed mirror."""
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [_FakeResponse(200, {"elements": []})],
        "https://b.example/api/interpreter": [_FakeResponse(503), _FakeResponse(503)],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        elements = provider._overpass_query("[out:json];();out;")

    assert elements == []


def test_overpass_empty_answer_does_not_pre_empt_real_data():
    """A mirror that answers 200-with-no-elements must not win over real data."""
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [_FakeResponse(200, {"elements": []})],
        "https://b.example/api/interpreter": [_FakeResponse(200, {"elements": [{"id": 9}]})],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        elements = provider._overpass_query("[out:json];();out;")

    assert elements == [{"id": 9}]


def test_overpass_moves_past_a_mirror_that_drops_the_connection():
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [httpx.ConnectError("boom")],
        "https://b.example/api/interpreter": [_FakeResponse(200, {"elements": [{"id": 2}]})],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        elements = provider._overpass_query("[out:json];();out;")

    assert elements == [{"id": 2}]
    assert len(client.calls) == 2, "a dead mirror must not swallow the request"


def test_overpass_recovers_when_a_mirror_answers_on_the_second_round():
    """Every mirror throttles the first round; one answers on the retry."""
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [_FakeResponse(503), _FakeResponse(200, {"elements": [{"id": 3}]})],
        "https://b.example/api/interpreter": [_FakeResponse(429), _FakeResponse(504)],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        elements = provider._overpass_query("[out:json];();out;")

    assert elements == [{"id": 3}]
    assert len(client.calls) == 3, "one retry round after every mirror failed once"


def test_overpass_raises_only_when_every_mirror_fails_both_rounds():
    provider = OpenStreetMapLocationProvider()
    endpoints = ["https://a.example", "https://b.example", "https://c.example"]
    client = _RecordingClient({
        "https://a.example": [_FakeResponse(504), _FakeResponse(500)],
        "https://b.example": [_FakeResponse(502), _FakeResponse(504)],
        "https://c.example": [_FakeResponse(500), _FakeResponse(503)],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client, endpoints)
    with endpoints_patch, client_patch, sleep_patch:
        with pytest.raises(LocationProviderUnavailable):
            provider._overpass_query("[out:json];();out;")

    assert len(client.calls) == 6, "each mirror is asked once per round, then the error surfaces"


def test_overpass_surfaces_an_invalid_request_when_no_mirror_succeeds():
    """A 400/422 cannot be fixed by another mirror; it must surface as 422."""
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [_FakeResponse(400), _FakeResponse(400)],
        "https://b.example/api/interpreter": [_FakeResponse(400), _FakeResponse(400)],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        with pytest.raises(LocationProviderInvalidRequest):
            provider._overpass_query("[out:json];();out;")

    assert len(client.calls) == 4, "every mirror was asked; none could serve the request"


def test_overpass_returns_an_empty_result_without_error():
    """A 200 with zero elements is a genuine 'nothing mapped' answer, not an error."""
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({"https://a.example/api/interpreter": [_FakeResponse(200, {"elements": []})]})
    endpoints_patch, client_patch, sleep_patch = _run(
        provider, client, ["https://a.example/api/interpreter"]
    )
    with endpoints_patch, client_patch, sleep_patch:
        elements = provider._overpass_query("[out:json];();out;")

    assert elements == []
    assert len(client.calls) == 1, "an empty answer from every mirror must not be retried"


def test_overpass_malformed_json_treats_that_mirror_as_unavailable():
    """A 200 whose body is not JSON is an unusable mirror, not a crash."""
    provider = OpenStreetMapLocationProvider()

    class _BadJsonClient:
        def __init__(self):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def post(self, url, data=None, **kwargs):
            self.calls += 1
            return _BrokenJsonResponse()

    client = _BadJsonClient()
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        with pytest.raises(LocationProviderUnavailable):
            provider._overpass_query("[out:json];();out;")

    assert client.calls == 4, "both mirrors are tried in both rounds"


_NANDYAL = (15.4736293, 78.4806592)


def _multi_client(elements_by_url: dict[str, list]) -> _RecordingClient:
    return _RecordingClient({
        url: [_FakeResponse(200, {"elements": elements})] for url, elements in elements_by_url.items()
    })


def test_nearby_multi_fetches_all_categories_in_one_query():
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [
            _FakeResponse(200, {
                "elements": [
                    {"tags": {"name": "Test Clinic", "amenity": "clinic"}, "lat": 15.4740, "lon": 78.4810},
                    {"tags": {"name": "Test School", "amenity": "school"}, "lat": 15.4750, "lon": 78.4830},
                ]
            })
        ],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        results = provider.nearby_multi(_NANDYAL[0], _NANDYAL[1], ["hospital", "school"], 5.0)

    assert len(client.calls) == 1, "one union query must serve every category"
    assert [p["name"] for p in results["hospital"]] == ["Test Clinic"]
    assert [p["name"] for p in results["school"]] == ["Test School"]


def test_nearby_multi_sends_one_merged_selector_per_tag_key():
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [_FakeResponse(200, {"elements": []})]
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        provider.nearby_multi(_NANDYAL[0], _NANDYAL[1], ["hospital", "school", "bank"], 5.0)

    sent = client.script_sent[-1]["data"]
    assert sent.count("nwr[") == 1, "hospital, school and bank are all amenity= values: one scan"
    assert '"amenity"~' in sent
    assert "bank" in sent and "school" in sent and "hospital" in sent


def test_nearby_multi_places_a_multi_tag_element_in_every_matching_category():
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({
        "https://a.example/api/interpreter": [
            _FakeResponse(200, {"elements": [{"tags": {"name": "Big Mall", "shop": "mall"}, "lat": 15.4740, "lon": 78.4810}]})
        ],
    })
    endpoints_patch, client_patch, sleep_patch = _run(provider, client)
    with endpoints_patch, client_patch, sleep_patch:
        results = provider.nearby_multi(_NANDYAL[0], _NANDYAL[1], ["shopping", "park"], 5.0)

    assert [p["name"] for p in results["shopping"]] == ["Big Mall"]
    assert results["park"] == []


def test_nearby_multi_rejects_unknown_categories():
    provider = OpenStreetMapLocationProvider()
    with pytest.raises(LocationProviderInvalidRequest):
        provider.nearby_multi(_NANDYAL[0], _NANDYAL[1], ["not_a_category"], 5.0)


def test_nearby_multi_uses_the_process_cache_before_the_network():
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({})

    from app.providers.openstreetmap import provider as provider_module

    key = "nearby_multi:hospital,school:15.47363:78.48066:5000"
    provider_module._cache.set(key, {"hospital": [{"name": "Cached"}]}, 300)
    try:
        results = provider.nearby_multi(_NANDYAL[0], _NANDYAL[1], ["hospital", "school"], 5.0)
    finally:
        provider_module._cache.get(key)

    assert results == {"hospital": [{"name": "Cached"}]}
    assert client.calls == []


def test_nearby_rejects_an_unknown_category():
    provider = OpenStreetMapLocationProvider()
    with pytest.raises(LocationProviderInvalidRequest):
        provider.nearby(15.47, 78.48, "not_a_category", 5.0)


def test_nearby_uses_the_process_cache_before_the_network():
    provider = OpenStreetMapLocationProvider()
    client = _RecordingClient({})

    from app.providers.openstreetmap import provider as provider_module

    key = "nearby:hospital:15.47360:78.48070:5000"
    provider_module._cache.set(key, [{"name": "Cached Hospital"}], 300)
    try:
        places = provider.nearby(15.4736, 78.4807, "hospital", 5.0)
    finally:
        provider_module._cache.get(key)

    assert places == [{"name": "Cached Hospital"}]
    assert client.calls == [], "a cache hit must not hit any mirror"
