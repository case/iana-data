"""Tests for download utilities."""

import shutil
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from src.utilities.download import download_iana_files

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SOURCE_FIXTURES_DIR = FIXTURES_DIR / "source" / "core"
METADATA_FIXTURES_DIR = FIXTURES_DIR / "metadata"


def load_fixture_headers(fixture_name):
    """Load HTTP headers from fixture file."""
    headers = {}
    headers_file = SOURCE_FIXTURES_DIR / f"{fixture_name}-headers.txt"
    with open(headers_file) as f:
        for line in f:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()
    return headers


def load_fixture_content(fixture_name):
    """Load content from fixture file."""
    content_file = SOURCE_FIXTURES_DIR / fixture_name
    return content_file.read_bytes()


def setup_test_env(tmp_path):
    """Setup test environment with directories."""
    source_dir = tmp_path / "data" / "source"
    generated_dir = tmp_path / "data" / "generated"
    source_dir.mkdir(parents=True)
    generated_dir.mkdir(parents=True)
    return source_dir, generated_dir


def test_download_first_time(tmp_path):
    """Test downloading files for the first time (no metadata)."""
    source_dir, generated_dir = setup_test_env(tmp_path)

    # Mock httpx responses with fixture data
    mock_responses = {
        "https://data.iana.org/rdap/dns.json": (
            200,
            load_fixture_headers("rdap-json"),
            load_fixture_content("rdap.json"),
        ),
        "https://data.iana.org/TLD/tlds-alpha-by-domain.txt": (
            200,
            load_fixture_headers("tlds-txt"),
            load_fixture_content("tlds.txt"),
        ),
        "https://www.iana.org/domains/root/db": (
            200,
            load_fixture_headers("root-html"),
            load_fixture_content("root.html"),
        ),
    }

    def mock_get(url, headers=None):
        status, resp_headers, content = mock_responses[url]
        response = Mock(spec=httpx.Response)
        response.status_code = status
        response.headers = resp_headers
        response.content = content
        response.text = content.decode("utf-8")
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(generated_dir / "metadata.json")),
        patch("httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_iana_files()

        # All files should be downloaded
        assert results["RDAP_BOOTSTRAP"] == "downloaded"
        assert results["TLD_LIST"] == "downloaded"
        assert results["ROOT_ZONE_DB"] == "downloaded"

        # Files should exist
        assert (source_dir / "iana-rdap.json").exists()
        assert (source_dir / "iana-tlds.txt").exists()
        assert (source_dir / "iana-root.html").exists()


def test_download_with_304_not_modified(tmp_path):
    """Test download when server returns 304 Not Modified."""
    source_dir, generated_dir = setup_test_env(tmp_path)

    # Copy existing file from fixtures
    shutil.copy(SOURCE_FIXTURES_DIR / "rdap.json", source_dir / "iana-rdap.json")

    # Copy metadata fixture with ETag/Last-Modified
    metadata_file = generated_dir / "metadata.json"
    shutil.copy(METADATA_FIXTURES_DIR / "valid-metadata.json", metadata_file)

    def mock_get(url, headers=None):
        # Return 304 for RDAP (has etag/last-modified in request)
        if url == "https://data.iana.org/rdap/dns.json":
            if headers and ("If-None-Match" in headers or "If-Modified-Since" in headers):
                response = Mock(spec=httpx.Response)
                response.status_code = 304
                response.headers = {}
                return response

        # Shouldn't get here in this test
        raise Exception(f"Unexpected request to {url}")

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(metadata_file)),
        patch("httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_iana_files()

        # Should return not_modified
        assert results["RDAP_BOOTSTRAP"] == "not_modified"


def test_download_with_fresh_cache(tmp_path):
    """Test download when cache is still fresh (no HTTP request made)."""
    source_dir, generated_dir = setup_test_env(tmp_path)

    # Copy existing file
    shutil.copy(SOURCE_FIXTURES_DIR / "rdap.json", source_dir / "iana-rdap.json")

    # Copy fresh cache metadata fixture
    metadata_file = generated_dir / "metadata.json"
    shutil.copy(METADATA_FIXTURES_DIR / "fresh-cache-metadata.json", metadata_file)

    request_made = False

    def mock_get(url, headers=None):
        nonlocal request_made
        request_made = True
        raise Exception("Should not make HTTP request when cache is fresh")

    # Mock "now" to be 1 hour after the fixture timestamp (within 24h cache window)
    # Fixture has last_downloaded: 2025-11-18T16:00:00Z with max_age: 86400
    from datetime import datetime, timezone

    mock_now = datetime(2025, 11, 18, 17, 0, 0, tzinfo=timezone.utc)

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(metadata_file)),
        patch("src.utilities.cache.datetime") as mock_datetime,
        patch("httpx.Client") as mock_client,
    ):
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_iana_files()

        # Should return not_modified without making request
        assert results["RDAP_BOOTSTRAP"] == "not_modified"
        assert not request_made  # No HTTP request should be made


def test_download_tld_list_content_unchanged(tmp_path):
    """Test TLD_LIST when content hasn't actually changed (only timestamp)."""
    source_dir, generated_dir = setup_test_env(tmp_path)

    # Copy baseline TLD file
    shutil.copy(SOURCE_FIXTURES_DIR / "tlds.txt", source_dir / "iana-tlds.txt")

    # Copy metadata fixture
    metadata_file = generated_dir / "metadata.json"
    shutil.copy(METADATA_FIXTURES_DIR / "valid-metadata.json", metadata_file)

    # Load timestamp-only change fixture
    timestamp_only_content = (SOURCE_FIXTURES_DIR / "tlds-timestamp-only.txt").read_text()

    def mock_get(url, headers=None):
        if url == "https://data.iana.org/TLD/tlds-alpha-by-domain.txt":
            response = Mock(spec=httpx.Response)
            response.status_code = 200
            response.headers = load_fixture_headers("tlds-txt")
            response.content = timestamp_only_content.encode("utf-8")
            response.text = timestamp_only_content
            return response
        raise Exception(f"Unexpected request to {url}")

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(metadata_file)),
        patch("httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_iana_files()

        # Should detect that content hasn't changed
        assert results["TLD_LIST"] == "not_modified"

        # File should not be updated
        current_content = (source_dir / "iana-tlds.txt").read_text()
        assert current_content == (SOURCE_FIXTURES_DIR / "tlds.txt").read_text()


def test_download_creates_source_directory(tmp_path):
    """Test that download creates source directory if it doesn't exist."""
    # Setup only generated dir (source doesn't exist)
    generated_dir = tmp_path / "data" / "generated"
    generated_dir.mkdir(parents=True)
    source_dir = tmp_path / "data" / "source"

    # Verify source dir doesn't exist
    assert not source_dir.exists()

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"Content-Type": "application/json"}
        response.content = b"{}"
        response.text = "{}"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(generated_dir / "metadata.json")),
        patch("httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        download_iana_files()

        # Source directory should be created
        assert source_dir.exists()


def test_download_handles_http_error(tmp_path):
    """Test that download handles HTTP errors gracefully."""
    source_dir, generated_dir = setup_test_env(tmp_path)

    def mock_get(url, headers=None):
        # Simulate connection error
        raise httpx.ConnectError("Connection failed")

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(generated_dir / "metadata.json")),
        patch("httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_iana_files()

        # All should return error
        assert results["RDAP_BOOTSTRAP"] == "error"
        assert results["TLD_LIST"] == "error"
        assert results["ROOT_ZONE_DB"] == "error"
