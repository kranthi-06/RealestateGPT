import pytest
import httpx
from unittest.mock import patch, MagicMock

from app.providers.web_search.searxng import SearXNGSearchProvider
from app.providers.web_search.models import (
    WebSearchInternalError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
)
from app.core.config import settings

@pytest.fixture
def searxng_provider():
    settings.SEARXNG_BASE_URL = "http://localhost:8080"
    return SearXNGSearchProvider()

def test_searxng_successful_response(searxng_provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "query": "test query",
        "results": [
            {
                "url": "https://example.com/property/1",
                "title": "2 BHK Flat",
                "content": "Nice 2 BHK flat for rent",
                "parsed_url": {"netloc": "example.com"}
            },
            {
                "url": "https://example.com/property/2",
                "title": "3 BHK House",
                "content": "Large house",
                "parsed_url": {"netloc": "example.com"}
            }
        ]
    }
    mock_response.elapsed.total_seconds.return_value = 0.5
    
    with patch("httpx.Client.get", return_value=mock_response):
        response = searxng_provider.search("test query")
        
        assert response.provider == "searxng"
        assert len(response.results) == 2
        assert response.results[0].title == "2 BHK Flat"
        assert response.results[0].url == "https://example.com/property/1"
        assert response.results[0].domain == "example.com"

def test_searxng_malformed_json(searxng_provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")
    
    with patch("httpx.Client.get", return_value=mock_response):
        with pytest.raises(WebSearchInternalError, match="SearXNG returned invalid JSON"):
            searxng_provider.search("test query")

def test_searxng_empty_response(searxng_provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": []}
    mock_response.elapsed.total_seconds.return_value = 0.1
    
    with patch("httpx.Client.get", return_value=mock_response):
        response = searxng_provider.search("test query")
        assert len(response.results) == 0

def test_searxng_timeout(searxng_provider):
    with patch("httpx.Client.get", side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(WebSearchTimeoutError, match="SearXNG request timed out"):
            searxng_provider.search("test query")

def test_searxng_connection_failure(searxng_provider):
    with patch("httpx.Client.get", side_effect=httpx.RequestError("Connection failed")):
        with pytest.raises(WebSearchInternalError, match="SearXNG request failed"):
            searxng_provider.search("test query")

def test_searxng_rate_limit(searxng_provider):
    mock_response = MagicMock()
    mock_response.status_code = 429
    
    with patch("httpx.Client.get", return_value=mock_response):
        with pytest.raises(WebSearchRateLimitError):
            searxng_provider.search("test query")

def test_searxng_http_error(searxng_provider):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("500 Error", request=MagicMock(), response=mock_response)
    
    with patch("httpx.Client.get", return_value=mock_response):
        with pytest.raises(WebSearchInternalError, match="SearXNG returned HTTP error 500"):
            searxng_provider.search("test query")

def test_searxng_normalization_and_domain_extraction(searxng_provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                # Missing parsed_url, should fallback to url parsing
                "url": "https://magicbricks.com/property/1",
                "title": "Fallback URL Parsing",
                "content": "Test content",
            },
            {
                # Missing url, should be skipped
                "title": "Missing URL",
                "content": "Test content",
            },
            {
                # Missing title, should be skipped
                "url": "https://example.com/2",
                "content": "Test content",
            }
        ]
    }
    mock_response.elapsed.total_seconds.return_value = 0.1
    
    with patch("httpx.Client.get", return_value=mock_response):
        response = searxng_provider.search("test query")
        assert len(response.results) == 1
        assert response.results[0].domain == "magicbricks.com"

def test_searxng_not_configured():
    settings.SEARXNG_BASE_URL = ""
    provider = SearXNGSearchProvider()
    with pytest.raises(WebSearchInternalError, match="SEARXNG_BASE_URL is not configured"):
        provider.search("test query")


def test_searxng_drops_dangerous_urls(searxng_provider):
    """SearXNG results must be sanitized at the provider layer (defense-in-depth)."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "url": "javascript:alert(1)",
                "title": "XSS attempt",
                "content": "evil",
                "parsed_url": {"netloc": "evil.test"},
            },
            {
                "url": "http://127.0.0.1/secret",
                "title": "Local SSRF",
                "content": "ssrf",
                "parsed_url": {"netloc": "127.0.0.1"},
            },
            {
                "url": "http://169.254.169.254/latest/meta-data/",
                "title": "Cloud metadata",
                "content": "metadata",
                "parsed_url": {"netloc": "169.254.169.254"},
            },
            {
                "url": "https://magicbricks.com/property/1",
                "title": "Safe result",
                "content": "Real listing",
                "parsed_url": {"netloc": "magicbricks.com"},
            },
        ]
    }
    mock_response.elapsed.total_seconds.return_value = 0.1

    with patch("httpx.Client.get", return_value=mock_response):
        response = searxng_provider.search("test query")
        assert len(response.results) == 1
        assert response.results[0].title == "Safe result"
        assert response.results[0].domain == "magicbricks.com"


def test_searxng_real_instance_payload_shape(searxng_provider):
    """A real SearXNG JSON payload must normalize without crashing.

    Live instances emit ``parsed_url`` as a 6-element array (not a dict) and may
    omit ``content`` entirely; both previously broke the normalization path.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "query": "2 bhk rent hyderabad",
        "number_of_results": 2,
        "results": [
            {
                "url": "https://www.magicbricks.com/property/1",
                "title": "2 BHK Flat for Rent in Hyderabad",
                "content": "Nice 2 BHK flat",
                "engine": "google",
                "parsed_url": ["https", "www.magicbricks.com", "/property/1", "", "", ""],
                "publishedDate": "2026-01-05T00:00:00",
                "thumbnail": "https://img.example/a.jpg",
            },
            {
                # No content and no single engine, only the aggregated engines list.
                "url": "https://housing.com/rent/2bhk",
                "title": "2BHK without a snippet",
                "parsed_url": ["https", "housing.com", "/rent/2bhk", "", "", ""],
                "engines": ["bing", "duckduckgo"],
            },
        ],
        "unresponsive_engines": [["brave", "too many requests"]],
    }
    mock_response.elapsed.total_seconds.return_value = 0.25

    with patch("httpx.Client.get", return_value=mock_response):
        response = searxng_provider.search("2 bhk rent hyderabad")

    assert len(response.results) == 2
    first, second = response.results

    assert first.domain == "magicbricks.com"
    assert first.description == "Nice 2 BHK flat"
    assert first.source_name == "google"
    assert first.thumbnail_url == "https://img.example/a.jpg"
    assert first.page_age == "2026-01-05T00:00:00"
    assert first.page_fetched is not None
    assert first.provider == "searxng"

    assert second.domain == "housing.com"
    assert second.description is None
    assert second.source_name == "bing, duckduckgo"
    assert second.page_fetched is None

    # number_of_results is honored for pagination metadata.
    assert response.total_results == 2
    assert response.more_results_available is False
    assert response.next_offset is None


def test_searxng_reports_more_results_only_when_instance_says_so(searxng_provider):
    """Pagination metadata is never invented when the instance omits a count."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "url": "https://magicbricks.com/property/1",
                "title": "One listing",
                "content": "snippet",
                "parsed_url": ["https", "magicbricks.com", "/property/1", "", "", ""],
            },
            {
                "url": "https://magicbricks.com/property/2",
                "title": "Two listing",
                "content": "snippet",
                "parsed_url": ["https", "magicbricks.com", "/property/2", "", "", ""],
            },
        ]
    }
    mock_response.elapsed.total_seconds.return_value = 0.1

    with patch("httpx.Client.get", return_value=mock_response):
        response = searxng_provider.search("test query", count=1)

    # count is applied locally to the fetched page.
    assert len(response.results) == 1
    assert response.total_results == 1
    assert response.more_results_available is False


def test_searxng_request_params_contract(searxng_provider):
    """``pageno``/``language``/``time_range`` are sent using SearXNG's vocabulary."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": []}
    mock_response.elapsed.total_seconds.return_value = 0.1

    with patch("httpx.Client.get", return_value=mock_response) as mock_get:
        searxng_provider.search("test query", language="en_IN", count=5, offset=5, freshness="pw")
        params = mock_get.call_args.kwargs["params"]

    assert params["q"] == "test query"
    assert params["format"] == "json"
    # offset 5 with a page size of 5 -> second page.
    assert params["pageno"] == 2
    assert params["language"] == "en-IN"
    assert params["time_range"] == "week"
    # SearXNG rejects unknown time_range values, so they are omitted entirely.
    assert "category" not in params and "country" not in params


def test_searxng_ignores_invalid_freshness_and_language(searxng_provider):
    """Unsupported hints are dropped rather than forwarded as invalid params."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": []}
    mock_response.elapsed.total_seconds.return_value = 0.1

    with patch("httpx.Client.get", return_value=mock_response) as mock_get:
        searxng_provider.search("test query", language="not a language", freshness="whenever")
        params = mock_get.call_args.kwargs["params"]

    assert "time_range" not in params
    assert "language" not in params
