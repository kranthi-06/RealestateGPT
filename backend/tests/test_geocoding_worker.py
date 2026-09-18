import pytest
from datetime import datetime, timezone

@pytest.fixture
def mongo():
    from app.core.database import connect, get_database, close_connection
    connect()
    db = get_database()
    yield db
    close_connection()

from unittest.mock import MagicMock, patch

from app.workers.geocoding import run_geocoding
from app.providers.location import LocationProviderUnavailable

@pytest.fixture
def test_db(mongo):
    mongo["properties"].delete_many({})
    mongo["geocode_cache"].delete_many({})
    mongo["worker_locks"].delete_many({})
    mongo["worker_runs"].delete_many({})
    yield mongo

@patch("app.workers.geocoding.get_location_provider")
@patch("app.workers.geocoding.time.sleep", return_value=None)
def test_geocoding_worker_processes_missing_coordinates(mock_sleep, mock_get_provider, test_db):
    mock_provider = MagicMock()
    mock_provider.name = "test_provider"
    mock_provider.geocode.return_value = {"latitude": 17.1, "longitude": 78.1, "provider": "test_provider"}
    mock_get_provider.return_value = mock_provider

    test_db["properties"].insert_many([
        {"_id": 1, "status": "active", "city": "Hyderabad", "locality": "A", "latitude": None, "longitude": None},
        {"_id": 2, "status": "active", "city": "Hyderabad", "locality": "B", "latitude": 17.0, "longitude": 78.0}, # Already has coords
        {"_id": 3, "status": "inactive", "city": "Hyderabad", "locality": "C", "latitude": None, "longitude": None}, # Inactive
    ])

    run_geocoding(test_db)

    assert mock_provider.geocode.call_count == 1
    mock_provider.geocode.assert_called_with("A, Hyderabad")

    # Verify update
    prop1 = test_db["properties"].find_one({"_id": 1})
    assert prop1["latitude"] == 17.1
    assert prop1["longitude"] == 78.1
    assert prop1["location_source"] == "test_provider"

    # Verify cache
    cache = test_db["geocode_cache"].find_one({"address": "A, Hyderabad"})
    assert cache["latitude"] == 17.1
    assert cache["provider"] == "test_provider"


@patch("app.workers.geocoding.get_location_provider")
@patch("app.workers.geocoding.time.sleep", return_value=None)
def test_geocoding_worker_uses_cache_and_does_not_repeat(mock_sleep, mock_get_provider, test_db):
    mock_provider = MagicMock()
    mock_get_provider.return_value = mock_provider

    test_db["geocode_cache"].insert_one({
        "address": "Cached, Hyderabad",
        "latitude": 17.2,
        "longitude": 78.2,
        "provider": "test_provider",
        "created_at": datetime.now(timezone.utc)
    })

    test_db["properties"].insert_one({
        "_id": 1, "status": "active", "city": "Hyderabad", "locality": "Cached", "latitude": None, "longitude": None
    })

    run_geocoding(test_db)

    # Provider should not be called because it was cached
    mock_provider.geocode.assert_not_called()

    prop1 = test_db["properties"].find_one({"_id": 1})
    assert prop1["latitude"] == 17.2
    assert prop1["longitude"] == 78.2


@patch("app.workers.geocoding.get_location_provider")
@patch("app.workers.geocoding.time.sleep", return_value=None)
def test_geocoding_worker_caches_failures(mock_sleep, mock_get_provider, test_db):
    mock_provider = MagicMock()
    mock_provider.name = "test_provider"
    mock_provider.geocode.side_effect = LocationProviderUnavailable("API error")
    mock_get_provider.return_value = mock_provider

    test_db["properties"].insert_one({
        "_id": 1, "status": "active", "city": "Hyderabad", "locality": "Fail", "latitude": None, "longitude": None
    })

    run_geocoding(test_db)

    # Verify failure cached
    cache = test_db["geocode_cache"].find_one({"address": "Fail, Hyderabad"})
    assert cache["latitude"] is None
    assert "API error" in cache["error"]

    prop1 = test_db["properties"].find_one({"_id": 1})
    assert prop1["latitude"] is None # Property is not updated


@patch("app.workers.geocoding.get_location_provider")
@patch("app.workers.geocoding.time.sleep", return_value=None)
def test_geocoding_worker_concurrent_lock(mock_sleep, mock_get_provider, test_db):
    # Simulate an active lock
    test_db["worker_locks"].insert_one({
        "_id": "geocoding_worker_lock",
        "locked_until": datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + 300, tz=timezone.utc)
    })

    mock_provider = MagicMock()
    mock_get_provider.return_value = mock_provider

    test_db["properties"].insert_one({
        "_id": 1, "status": "active", "city": "Hyderabad", "locality": "A", "latitude": None, "longitude": None
    })

    run_geocoding(test_db)

    # Provider should not be called because worker is locked
    mock_provider.geocode.assert_not_called()


@patch("app.workers.geocoding.get_location_provider")
@patch("app.workers.geocoding.time.sleep", return_value=None)
def test_geocoding_worker_consumes_queue(mock_sleep, mock_get_provider, test_db):
    """Queue items inserted by ingestion are drained first."""
    mock_provider = MagicMock()
    mock_provider.name = "test_provider"
    mock_provider.geocode.return_value = {"latitude": 17.5, "longitude": 78.5}
    mock_get_provider.return_value = mock_provider

    test_db["properties"].insert_one({
        "_id": 11, "status": "active", "city": "Hyderabad", "locality": "Queued", "latitude": None, "longitude": None
    })
    test_db["geocode_queue"].insert_one({
        "property_id": 11,
        "address": "Queued, Hyderabad",
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })

    run_geocoding(test_db)

    mock_provider.geocode.assert_called_with("Queued, Hyderabad")
    prop = test_db["properties"].find_one({"_id": 11})
    assert prop["latitude"] == 17.5
    queue_item = test_db["geocode_queue"].find_one({"property_id": 11})
    assert queue_item["status"] == "completed"
