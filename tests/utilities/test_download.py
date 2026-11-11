"""Tests for download utilities."""

import json
import shutil
from datetime import UTC
from pathlib import Path
from unittest.mock import Mock, patch

import httpx2
import pytest

from src.utilities.download import (
    _download_file_impl,
    download_file,
    download_iana_files,
)
from src.utilities.metadata import utc_timestamp
from tests.dated_fixtures import latest_fixture

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SOURCE_FIXTURES_DIR = FIXTURES_DIR / "source" / "core"
METADATA_FIXTURES_DIR = FIXTURES_DIR / "metadata"
IANA_TLDS_FIXTURE = latest_fixture(SOURCE_FIXTURES_DIR, "iana-tlds.json")
IANA_TLDS_SCHEMA_FIXTURE = latest_fixture(SOURCE_FIXTURES_DIR, "iana-tlds-schema.json")


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

    # Mock httpx2 responses with fixture data
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
        "https://data.iana.org/TLD/v1/tlds.json": (
            200,
            {},
            IANA_TLDS_FIXTURE.read_bytes(),
        ),
        "https://data.iana.org/TLD/v1/tlds-schema.json": (
            200,
            {},
            IANA_TLDS_SCHEMA_FIXTURE.read_bytes(),
        ),
    }

    def mock_get(url, headers=None):
        status, resp_headers, content = mock_responses[url]
        response = Mock(spec=httpx2.Response)
        response.status_code = status
        response.headers = resp_headers
        response.content = content
        response.text = content.decode("utf-8")
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch(
            "src.utilities.metadata.METADATA_FILE", str(generated_dir / "metadata.json")
        ),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_iana_files()

        # All files should be downloaded
        assert results["RDAP_BOOTSTRAP"] == "downloaded"
        assert results["TLD_LIST"] == "downloaded"
        assert results["IANA_TLDS"] == "downloaded"
        assert results["IANA_TLDS_SCHEMA"] == "downloaded"

        # Files should exist
        assert (source_dir / "iana-rdap.json").exists()
        assert (source_dir / "iana-tlds.txt").exists()
        assert (source_dir / "iana-tlds.json").read_bytes() == (
            IANA_TLDS_FIXTURE.read_bytes()
        )
        assert (source_dir / "iana-tlds-schema.json").exists()


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
        if (
            url == "https://data.iana.org/rdap/dns.json"
            and headers
            and ("If-None-Match" in headers or "If-Modified-Since" in headers)
        ):
            response = Mock(spec=httpx2.Response)
            response.status_code = 304
            response.headers = {}
            return response

        # Shouldn't get here in this test
        raise AssertionError(f"Unexpected request to {url}")

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(metadata_file)),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_iana_files()

        # Should return not_modified
        assert results["RDAP_BOOTSTRAP"] == "not_modified"


def test_download_with_fresh_cache(tmp_path):
    """Test download when cache is still fresh (no HTTP request made for cached file)."""
    source_dir, generated_dir = setup_test_env(tmp_path)

    # Copy existing files
    shutil.copy(SOURCE_FIXTURES_DIR / "rdap.json", source_dir / "iana-rdap.json")
    shutil.copy(SOURCE_FIXTURES_DIR / "tlds.txt", source_dir / "iana-tlds.txt")
    shutil.copy(IANA_TLDS_FIXTURE, source_dir / "iana-tlds.json")

    # Copy fresh cache metadata fixture
    metadata_file = generated_dir / "metadata.json"
    shutil.copy(METADATA_FIXTURES_DIR / "fresh-cache-metadata.json", metadata_file)

    iana_tlds_request_made = False

    def mock_get(url, headers=None):
        # RDAP and TLD_LIST should still make requests (but get 304 responses)
        if (
            url == "https://data.iana.org/rdap/dns.json"
            or url == "https://data.iana.org/TLD/tlds-alpha-by-domain.txt"
            or url == "https://data.iana.org/TLD/v1/tlds-schema.json"
        ):
            response = Mock(spec=httpx2.Response)
            response.status_code = 304
            response.headers = {}
            return response
        elif url == "https://data.iana.org/TLD/v1/tlds.json":
            # IANA_TLDS should NOT make a request (cache is fresh)
            nonlocal iana_tlds_request_made
            iana_tlds_request_made = True
            raise AssertionError(
                "Should not make HTTP request for IANA_TLDS when cache is fresh"
            )
        raise AssertionError(f"Unexpected URL: {url}")

    # Mock "now" to be 1 hour after the fixture timestamp (within 24h cache window)
    # Fixture has last_downloaded: 2025-11-18T16:00:00Z with max_age: 86400
    from datetime import datetime

    mock_now = datetime(2025, 11, 18, 17, 0, 0, tzinfo=UTC)

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(metadata_file)),
        patch("src.utilities.cache.datetime") as mock_datetime,
        patch("httpx2.Client") as mock_client,
    ):
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_iana_files()

        # IANA_TLDS should skip HTTP request due to fresh cache
        assert results["IANA_TLDS"] == "not_modified"
        assert not iana_tlds_request_made

        # RDAP and TLD_LIST should still make requests but get 304
        assert results["RDAP_BOOTSTRAP"] == "not_modified"
        assert results["TLD_LIST"] == "not_modified"


def test_download_tld_list_content_unchanged(tmp_path):
    """Test TLD_LIST when content hasn't actually changed (only timestamp)."""
    source_dir, generated_dir = setup_test_env(tmp_path)

    # Copy baseline TLD file
    shutil.copy(SOURCE_FIXTURES_DIR / "tlds.txt", source_dir / "iana-tlds.txt")

    # Copy metadata fixture
    metadata_file = generated_dir / "metadata.json"
    shutil.copy(METADATA_FIXTURES_DIR / "valid-metadata.json", metadata_file)

    # Load timestamp-only change fixture
    timestamp_only_content = (
        SOURCE_FIXTURES_DIR / "tlds-timestamp-only.txt"
    ).read_text()

    def mock_get(url, headers=None):
        if url == "https://data.iana.org/TLD/tlds-alpha-by-domain.txt":
            response = Mock(spec=httpx2.Response)
            response.status_code = 200
            response.headers = load_fixture_headers("tlds-txt")
            response.content = timestamp_only_content.encode("utf-8")
            response.text = timestamp_only_content
            return response
        raise AssertionError(f"Unexpected request to {url}")

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(metadata_file)),
        patch("httpx2.Client") as mock_client,
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
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {"Content-Type": "application/json"}
        response.content = b"{}"
        response.text = "{}"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch(
            "src.utilities.metadata.METADATA_FILE", str(generated_dir / "metadata.json")
        ),
        patch("httpx2.Client") as mock_client,
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
        raise httpx2.ConnectError("Connection failed")

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch(
            "src.utilities.metadata.METADATA_FILE", str(generated_dir / "metadata.json")
        ),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_iana_files()

        # All should return error
        assert results["RDAP_BOOTSTRAP"] == "error"
        assert results["TLD_LIST"] == "error"
        assert results["IANA_TLDS"] == "error"
        assert results["IANA_TLDS_SCHEMA"] == "error"


def test_download_file_impl_single_file(tmp_path):
    """Test _download_file_impl() function directly for a single file."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    filepath = source_dir / "test-file.csv"

    # Mock response
    def mock_request(client, url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {
            "etag": '"abc123"',
            "last-modified": "Wed, 20 Nov 2024 12:00:00 GMT",
        }
        response.content = b"col1,col2\nval1,val2\n"
        response.text = "col1,col2\nval1,val2\n"
        return response

    metadata: dict = {}

    with patch(
        "src.utilities.download.make_request_with_retry", side_effect=mock_request
    ):
        mock_client = Mock(spec=httpx2.Client)
        result = _download_file_impl(
            client=mock_client,
            key="TEST_FILE",
            url="https://example.com/test.csv",
            filepath=filepath,
            metadata=metadata,
        )

    # Check result
    assert result == "downloaded"
    assert filepath.exists()
    assert filepath.read_text() == "col1,col2\nval1,val2\n"

    # Check metadata was updated
    assert "TEST_FILE" in metadata
    assert metadata["TEST_FILE"]["cache_data"]["etag"] == '"abc123"'
    assert "last_checked" in metadata["TEST_FILE"]


def test_download_file_impl_304_not_modified(tmp_path):
    """Test _download_file_impl() with 304 Not Modified response."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    filepath = source_dir / "test-file.csv"

    # Create existing file
    filepath.write_text("existing content")

    # Mock 304 response
    def mock_request(client, url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 304
        response.headers = {}
        return response

    metadata = {
        "TEST_FILE": {
            "cache_data": {
                "etag": '"abc123"',
                "last_modified": "Wed, 20 Nov 2024 12:00:00 GMT",
            }
        }
    }

    with patch(
        "src.utilities.download.make_request_with_retry", side_effect=mock_request
    ):
        mock_client = Mock(spec=httpx2.Client)
        result = _download_file_impl(
            client=mock_client,
            key="TEST_FILE",
            url="https://example.com/test.csv",
            filepath=filepath,
            metadata=metadata,
        )

    # Check result
    assert result == "not_modified"

    # File should be unchanged
    assert filepath.read_text() == "existing content"


def test_download_file_impl_with_content_validator(tmp_path):
    """Test _download_file_impl() with content validator callback."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    filepath = source_dir / "test-file.txt"

    # Create existing file
    filepath.write_text("existing content")

    # Mock response with new content
    def mock_request(client, url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {}
        response.content = b"new content"
        response.text = "new content"
        return response

    # Validator that returns False (content not actually changed)
    def validator(path, new_content):
        return False  # Pretend content hasn't changed

    metadata: dict = {}

    with patch(
        "src.utilities.download.make_request_with_retry", side_effect=mock_request
    ):
        mock_client = Mock(spec=httpx2.Client)
        result = _download_file_impl(
            client=mock_client,
            key="TEST_FILE",
            url="https://example.com/test.txt",
            filepath=filepath,
            metadata=metadata,
            content_validator=validator,
        )

    # Check result - should be not_modified because validator returned False
    assert result == "not_modified"

    # File should be unchanged
    assert filepath.read_text() == "existing content"


def test_download_file_public_api(tmp_path):
    """Test the public download_file() API that handles everything."""
    source_dir = tmp_path / "data" / "source"
    generated_dir = tmp_path / "data" / "generated"

    # Mock response
    def mock_request(client, url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {
            "etag": '"test-etag"',
        }
        response.content = b"test,data\n1,2\n"
        response.text = "test,data\n1,2\n"
        return response

    # Ensure generated dir exists for metadata
    generated_dir.mkdir(parents=True)

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch(
            "src.utilities.metadata.METADATA_FILE", str(generated_dir / "metadata.json")
        ),
        patch(
            "src.utilities.download.make_request_with_retry", side_effect=mock_request
        ),
        patch("src.utilities.download.httpx2.Client") as mock_client_class,
    ):
        # Setup mock client context manager
        mock_client_class.return_value.__enter__.return_value = Mock()
        mock_client_class.return_value.__exit__.return_value = False

        result = download_file(
            key="TEST_FILE",
            url="https://example.com/test.csv",
            filename="test-file.csv",
        )

    # Check result
    assert result == "downloaded"

    # Check file was created
    assert (source_dir / "test-file.csv").exists()
    assert (source_dir / "test-file.csv").read_text() == "test,data\n1,2\n"


def test_download_file_impl_with_cache_control_header(tmp_path):
    """Test _download_file_impl() with Cache-Control header (covers lines 305-312)."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    filepath = source_dir / "test-file.html"

    # Mock response with Cache-Control header
    def mock_request(client, url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {
            "cache-control": "public, max-age=86400",
            "etag": '"cache-test"',
        }
        response.content = b"<html>cached content</html>"
        response.text = "<html>cached content</html>"
        return response

    metadata: dict = {}

    with patch(
        "src.utilities.download.make_request_with_retry", side_effect=mock_request
    ):
        mock_client = Mock(spec=httpx2.Client)
        result = _download_file_impl(
            client=mock_client,
            key="CACHED_FILE",
            url="https://example.com/cached.html",
            filepath=filepath,
            metadata=metadata,
        )

    # Check result
    assert result == "downloaded"
    assert filepath.exists()

    # Check metadata has cache-control data
    assert "CACHED_FILE" in metadata
    assert "cache_data" in metadata["CACHED_FILE"]
    assert (
        metadata["CACHED_FILE"]["cache_data"]["cache_control"]
        == "public, max-age=86400"
    )
    assert metadata["CACHED_FILE"]["cache_data"]["cache_max_age"] == "86400"
    assert "last_downloaded" in metadata["CACHED_FILE"]["cache_data"]


def test_download_file_impl_with_http_error_status(tmp_path):
    """Test _download_file_impl() returns error for non-200/304 status (covers line 316)."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    filepath = source_dir / "test-file.txt"

    # Mock response with 500 error
    def mock_request(client, url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 500  # Server error
        response.headers = {}
        return response

    metadata: dict = {}

    with patch(
        "src.utilities.download.make_request_with_retry", side_effect=mock_request
    ):
        mock_client = Mock(spec=httpx2.Client)
        result = _download_file_impl(
            client=mock_client,
            key="ERROR_FILE",
            url="https://example.com/error.txt",
            filepath=filepath,
            metadata=metadata,
        )

    # Check result is error
    assert result == "error"


def test_download_file_impl_cache_fresh_initializes_metadata(tmp_path):
    """Test that cache fresh check initializes metadata if key missing (covers line 256)."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    filepath = source_dir / "test-file.html"

    # Create existing file
    filepath.write_text("existing cached content")

    # Mock datetime for cache freshness check
    from datetime import datetime

    mock_now = datetime(2025, 11, 18, 17, 0, 0, tzinfo=UTC)

    # Metadata with fresh cache but key not yet in metadata dict
    metadata: dict = {}

    # We need to bypass the is_cache_fresh check by having valid cache data
    # First, let's create metadata with fresh cache
    metadata["TEST_KEY"] = {
        "cache_data": {
            "cache_control": "public, max-age=86400",
            "cache_max_age": "86400",
            "last_downloaded": "2025-11-18T16:00:00Z",  # 1 hour ago
        }
    }

    with (
        patch("src.utilities.download.is_cache_fresh", return_value=True),
        patch("src.utilities.cache.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat

        mock_client = Mock(spec=httpx2.Client)
        result = _download_file_impl(
            client=mock_client,
            key="TEST_KEY",
            url="https://example.com/test.html",
            filepath=filepath,
            metadata=metadata,
        )

    # Check result
    assert result == "not_modified"
    # Metadata should have last_checked updated
    assert "last_checked" in metadata["TEST_KEY"]


def test_download_iptoasn_success(tmp_path):
    """A successful iptoasn download writes the file and records last_downloaded."""
    from src.utilities.download import download_iptoasn
    from src.utilities.metadata import load_metadata

    iptoasn_dir = tmp_path / "data" / "source" / "iptoasn"

    # Mock response
    def mock_request(client, url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.content = b"fake gzip content"
        return response

    with (
        patch("src.utilities.download.IPTOASN_DIR", str(iptoasn_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(tmp_path / "metadata.json")),
        patch(
            "src.utilities.download.make_request_with_retry", side_effect=mock_request
        ),
        patch("httpx2.Client") as mock_client_class,
    ):
        mock_client_class.return_value.__enter__.return_value = Mock()
        mock_client_class.return_value.__exit__.return_value = False

        result = download_iptoasn()
        metadata = load_metadata()

    assert result == "downloaded"
    assert (iptoasn_dir / "ip2asn-combined.tsv.gz").exists()
    assert (iptoasn_dir / "ip2asn-combined.tsv.gz").read_bytes() == b"fake gzip content"
    assert metadata["IPTOASN"]["last_downloaded"]


def test_download_iptoasn_http_error(tmp_path):
    """Test download_iptoasn handles HTTP errors."""
    from src.utilities.download import download_iptoasn

    iptoasn_dir = tmp_path / "data" / "source" / "iptoasn"

    # Mock 404 response
    def mock_request(client, url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 404
        return response

    with (
        patch("src.utilities.download.IPTOASN_DIR", str(iptoasn_dir)),
        patch(
            "src.utilities.download.make_request_with_retry", side_effect=mock_request
        ),
        patch("httpx2.Client") as mock_client_class,
    ):
        mock_client_class.return_value.__enter__.return_value = Mock()
        mock_client_class.return_value.__exit__.return_value = False

        result = download_iptoasn()

    assert result == "error"


def test_download_iptoasn_exception(tmp_path):
    """Test download_iptoasn handles exceptions."""
    from src.utilities.download import download_iptoasn

    iptoasn_dir = tmp_path / "data" / "source" / "iptoasn"

    # Mock exception
    def mock_request(client, url, headers=None):
        raise RuntimeError("Connection failed")

    with (
        patch("src.utilities.download.IPTOASN_DIR", str(iptoasn_dir)),
        patch(
            "src.utilities.download.make_request_with_retry", side_effect=mock_request
        ),
        patch("httpx2.Client") as mock_client_class,
    ):
        mock_client_class.return_value.__enter__.return_value = Mock()
        mock_client_class.return_value.__exit__.return_value = False

        result = download_iptoasn()

    assert result == "error"


def test_get_iptoasn_path():
    """Test get_iptoasn_path returns correct path."""
    from src.utilities.download import get_iptoasn_path

    path = get_iptoasn_path()

    assert path.name == "ip2asn-combined.tsv.gz"
    assert "iptoasn" in str(path)


def test_download_file_applies_transform_before_saving(tmp_path):
    """A transform converts the fetched document into the bytes written to disk."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {}
        response.content = b"<html>raw</html>"
        response.text = "<html>raw</html>"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value={}),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.csv",
            transform=lambda text: f"derived:{len(text)}".encode(),
        )

    assert result == "downloaded"
    assert (source_dir / "out.csv").read_bytes() == b"derived:16"


def test_download_file_skips_write_when_transform_output_unchanged(tmp_path):
    """An unchanged derived file is not rewritten, so the source document can churn."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    existing = source_dir / "out.csv"
    existing.write_bytes(b"derived:16")
    original_mtime = existing.stat().st_mtime_ns

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {}
        response.content = b"<html>new</html>"
        response.text = "<html>new</html>"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value={}),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.csv",
            transform=lambda text: f"derived:{len(text)}".encode(),
        )

    assert result == "not_modified"
    assert existing.stat().st_mtime_ns == original_mtime


def test_download_file_reports_error_when_transform_raises(tmp_path):
    """A transform that rejects the document fails the download instead of saving it."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {}
        response.content = b"<html>unexpected</html>"
        response.text = "<html>unexpected</html>"
        return response

    def exploding_transform(text):
        raise ValueError("page structure changed")

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value={}),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.csv",
            transform=exploding_transform,
        )

    assert result == "error"
    assert not (source_dir / "out.csv").exists()


def test_download_file_drops_cache_recorded_against_another_url(tmp_path):
    """Repointing a key at a new URL discards the old endpoint's validators."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    metadata = {
        "TEST": {
            "cache_data": {
                "url": "https://example.com/old-endpoint",
                "etag": 'W/"stale"',
                "last_modified": "Tue, 26 May 2026 03:09:30 GMT",
            }
        }
    }
    sent_headers = {}

    def mock_get(url, headers=None):
        sent_headers.update(headers or {})
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {"etag": 'W/"fresh"'}
        response.content = b"<html>page</html>"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value=metadata),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.csv",
            transform=lambda text: f"derived:{len(text)}".encode(),
        )

    assert result == "downloaded"
    assert "If-None-Match" not in sent_headers
    assert "If-Modified-Since" not in sent_headers
    assert metadata["TEST"]["cache_data"] == {
        "url": "https://example.com/page",
        "etag": 'W/"fresh"',
    }


def test_download_file_reuses_cache_recorded_against_the_same_url(tmp_path):
    """Validators captured from the same URL are still sent as conditional headers."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    metadata = {
        "TEST": {
            "cache_data": {
                "url": "https://example.com/page",
                "etag": 'W/"same"',
            }
        }
    }
    sent_headers = {}

    def mock_get(url, headers=None):
        sent_headers.update(headers or {})
        response = Mock(spec=httpx2.Response)
        response.status_code = 304
        response.headers = {}
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value=metadata),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST", url="https://example.com/page", filename="out.csv"
        )

    assert result == "not_modified"
    assert sent_headers["If-None-Match"] == 'W/"same"'


def test_download_file_records_new_etag_when_transform_output_is_unchanged(tmp_path):
    """An unchanged derived file still refreshes the validators, so 304s keep working."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "out.csv").write_bytes(b"derived:20")
    metadata = {
        "TEST": {"cache_data": {"url": "https://example.com/page", "etag": 'W/"old"'}}
    }

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {"etag": 'W/"new"'}
        response.content = b"<html>churned</html>"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value=metadata),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.csv",
            transform=lambda text: f"derived:{len(text)}".encode(),
        )

    assert result == "not_modified"
    assert metadata["TEST"]["cache_data"]["etag"] == 'W/"new"'


def test_download_file_transform_never_runs_on_a_304(tmp_path):
    """A 304 short-circuits before the transform, so the file on disk is untouched."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "out.csv").write_bytes(b"existing")
    metadata = {
        "TEST": {"cache_data": {"url": "https://example.com/page", "etag": 'W/"same"'}}
    }
    calls = []

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 304
        response.headers = {}
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value=metadata),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.csv",
            transform=lambda text: calls.append(text) or b"derived",
        )

    assert result == "not_modified"
    assert calls == []
    assert (source_dir / "out.csv").read_bytes() == b"existing"


def test_download_file_transform_decodes_utf8_regardless_of_declared_charset(tmp_path):
    """The transform sees UTF-8, not httpx2's header-inferred charset."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {"content-type": "text/html; charset=iso-8859-1"}
        response.content = "Kanton Zürich".encode()
        response.text = "Kanton ZÃ¼rich"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value={}),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.csv",
            transform=lambda text: text.encode("utf-8"),
        )

    assert result == "downloaded"
    assert (source_dir / "out.csv").read_text(encoding="utf-8") == "Kanton Zürich"


def test_download_file_records_validators_when_content_validator_reports_unchanged(
    tmp_path,
):
    """A source whose content never changes keeps sending conditional requests."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    metadata = {"TEST": {}}

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {"etag": 'W/"new"'}
        response.content = b"same"
        response.text = "same"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value=metadata),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.txt",
            content_validator=lambda path, text: False,
        )

    assert result == "not_modified"
    assert metadata["TEST"]["cache_data"] == {
        "url": "https://example.com/page",
        "etag": 'W/"new"',
    }


def test_download_file_ignores_cache_freshness_when_a_transform_is_set(tmp_path):
    """A long origin max-age must not skip the transform and freeze the derived file."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    metadata = {
        "TEST": {
            "cache_data": {
                "url": "https://example.com/page",
                "cache_control": "max-age=604800",
                "cache_max_age": "604800",
                "last_downloaded": utc_timestamp(),
            }
        }
    }
    requested = []

    def mock_get(url, headers=None):
        requested.append(url)
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {}
        response.content = b"<html>fresh</html>"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value=metadata),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.csv",
            transform=lambda text: b"derived",
        )

    assert requested == ["https://example.com/page"]
    assert result == "downloaded"
    assert (source_dir / "out.csv").read_bytes() == b"derived"


def test_download_file_does_not_record_validators_when_transform_raises(tmp_path):
    """A failed transform must be retried, not answered with a 304 next run."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    metadata = {"TEST": {}}

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {"etag": 'W/"changed-markup"'}
        response.content = b"<html>redesigned</html>"
        return response

    def exploding_transform(text):
        raise ValueError("page structure changed")

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value=metadata),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.csv",
            transform=exploding_transform,
        )

    assert result == "error"
    assert "cache_data" not in metadata["TEST"]


def test_download_file_keeps_freshness_window_anchored_to_the_last_real_save(tmp_path):
    """An unchanged source must not slide its own Cache-Control window forward."""
    source_dir = tmp_path / "data" / "source"
    source_dir.mkdir(parents=True)
    anchored = "2026-01-01T00:00:00Z"
    metadata = {
        "TEST": {
            "cache_data": {
                "url": "https://example.com/page",
                "cache_control": "max-age=3600",
                "cache_max_age": "3600",
                "last_downloaded": anchored,
            }
        }
    }

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        response.status_code = 200
        response.headers = {"cache-control": "max-age=3600", "etag": 'W/"new"'}
        response.content = b"same"
        response.text = "same"
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.download.load_metadata", return_value=metadata),
        patch("src.utilities.download.save_metadata"),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        result = download_file(
            key="TEST",
            url="https://example.com/page",
            filename="out.txt",
            content_validator=lambda path, text: False,
        )

    assert result == "not_modified"
    assert metadata["TEST"]["cache_data"]["last_downloaded"] == anchored
    assert metadata["TEST"]["cache_data"]["etag"] == 'W/"new"'


# --- IANA TLD JSON and its schema: checked before either replaces a stored file ---

IANA_TLDS_URL = "https://data.iana.org/TLD/v1/tlds.json"
IANA_TLDS_SCHEMA_URL = "https://data.iana.org/TLD/v1/tlds-schema.json"
STORED_DATA = IANA_TLDS_FIXTURE.read_bytes()
STORED_SCHEMA = IANA_TLDS_SCHEMA_FIXTURE.read_bytes()


def _download_with(tmp_path, bodies, *, stored=None):
    """Run download_iana_files over ``bodies``; a URL not in it answers 304.

    Stores the fixture pair first by default. Returns (results, source_dir, metadata).
    """
    source_dir, generated_dir = setup_test_env(tmp_path)
    if stored is None:
        stored = {"iana-tlds.json": STORED_DATA, "iana-tlds-schema.json": STORED_SCHEMA}
    for name, content in stored.items():
        (source_dir / name).write_bytes(content)
    metadata_file = generated_dir / "metadata.json"

    def mock_get(url, headers=None):
        response = Mock(spec=httpx2.Response)
        body = bodies.get(url)
        if isinstance(body, Exception):
            raise body
        if body is None:
            response.status_code = 304
            response.headers = {}
            return response
        response.status_code = 200
        response.headers = {"etag": '"fresh"'}
        response.content = body
        response.text = body.decode("utf-8", errors="replace")
        return response

    with (
        patch("src.utilities.download.SOURCE_DIR", str(source_dir)),
        patch("src.utilities.metadata.METADATA_FILE", str(metadata_file)),
        patch("httpx2.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get
        results = download_iana_files()

    return results, source_dir, json.loads(metadata_file.read_text())


def _data(mutate=None, **meta):
    """The TLD JSON fixture as bytes, with ``meta`` updated and ``mutate`` applied."""
    document = json.loads(STORED_DATA)
    document["meta"].update(meta)
    if mutate is not None:
        mutate(document)
    return json.dumps(document).encode("utf-8")


def _schema(mutate):
    """The schema fixture as bytes, with ``mutate`` applied."""
    schema = json.loads(STORED_SCHEMA)
    mutate(schema)
    return json.dumps(schema).encode("utf-8")


def _stored_names(source_dir):
    return sorted(p.name for p in source_dir.iterdir())


PAIR = ["iana-tlds-schema.json", "iana-tlds.json"]


def test_iana_tlds_changed_payload_replaces_the_stored_file(tmp_path):
    def change(document):
        document["domains"][0]["whois_server"] = "whois.changed.example"

    body = _data(change)

    results, source_dir, metadata = _download_with(tmp_path, {IANA_TLDS_URL: body})

    assert results["IANA_TLDS"] == "downloaded"
    assert (source_dir / "iana-tlds.json").read_bytes() == body
    assert metadata["IANA_TLDS"]["cache_data"]["etag"] == '"fresh"'
    assert _stored_names(source_dir) == PAIR


def test_iana_tlds_timestamp_only_change_keeps_the_stored_bytes(tmp_path):
    body = _data(generated="2026-12-01T00:00:00+00:00")
    assert body != STORED_DATA

    results, source_dir, _ = _download_with(tmp_path, {IANA_TLDS_URL: body})

    assert results["IANA_TLDS"] == "not_modified"
    assert (source_dir / "iana-tlds.json").read_bytes() == STORED_DATA


def _ftp_registration_url(document):
    document["domains"][0]["registration_url"] = "ftp://nic.example"


def _rdap_without_trailing_slash(document):
    document["domains"][0]["rdap_base_urls"] = ["https://rdap.example"]


def _ds_key_tag_out_of_range(document):
    document["domains"][0]["ds_records"][0]["key_tag"] = 70000


def _retired_with_nameservers(document):
    document["domains"][0]["status"] = "retired"


@pytest.mark.parametrize(
    "body",
    [
        b"<html>503 Service Unavailable</html>",
        b"",
        b"\xff\xfe not utf-8",
        b"[]",
        b'{"meta": {"specversion": 1}, "domains": []}',
        _data(specversion=2),
        _data(_ftp_registration_url),
        _data(_rdap_without_trailing_slash),
        _data(_ds_key_tag_out_of_range),
        _data(_retired_with_nameservers),
    ],
    ids=[
        "html",
        "empty",
        "not-utf8",
        "array",
        "no-domains",
        "specversion-2",
        "schema-only-registration-url",
        "schema-only-rdap-slash",
        "schema-only-ds-range",
        "retired-with-nameservers",
    ],
)
def test_iana_tlds_invalid_payload_is_reported_and_never_stored(tmp_path, body):
    results, source_dir, metadata = _download_with(tmp_path, {IANA_TLDS_URL: body})

    assert results["IANA_TLDS"] == "invalid"
    assert (source_dir / "iana-tlds.json").read_bytes() == STORED_DATA
    # No validators: the next run must fetch again rather than be answered 304.
    assert "cache_data" not in metadata["IANA_TLDS"]
    assert _stored_names(source_dir) == PAIR


def test_iana_tlds_with_no_stored_schema_is_rejected_not_trusted(tmp_path):
    results, source_dir, _ = _download_with(
        tmp_path, {IANA_TLDS_URL: _data()}, stored={}
    )

    assert results["IANA_TLDS"] == "invalid"
    assert list(source_dir.iterdir()) == []


def test_iana_tlds_fetch_failure_is_an_error_and_keeps_the_stored_file(tmp_path):
    results, source_dir, _ = _download_with(
        tmp_path, {IANA_TLDS_URL: httpx2.ConnectError("Connection failed")}
    )

    assert results["IANA_TLDS"] == "error"
    assert (source_dir / "iana-tlds.json").read_bytes() == STORED_DATA


def _drop_id(schema):
    del schema["$id"]


def _other_id(schema):
    schema["$id"] = "https://example.com/other-schema.json"


def _malformed(schema):
    schema["type"] = 7


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b"{}",
        _schema(_drop_id),
        _schema(_other_id),
        _schema(_malformed),
        b'{"$id": "https://data.iana.org/TLD/v1/tlds-schema.json", "type": "object"}',
    ],
    ids=[
        "not-json",
        "array",
        "accepts-everything",
        "no-id",
        "another-schema",
        "malformed-schema",
        "no-record-definition",
    ],
)
def test_iana_tlds_schema_invalid_payload_is_reported_and_never_stored(tmp_path, body):
    results, source_dir, metadata = _download_with(
        tmp_path, {IANA_TLDS_SCHEMA_URL: body}
    )

    assert results["IANA_TLDS_SCHEMA"] == "invalid"
    assert (source_dir / "iana-tlds-schema.json").read_bytes() == STORED_SCHEMA
    assert "cache_data" not in metadata["IANA_TLDS_SCHEMA"]
    assert _stored_names(source_dir) == PAIR


def _add_description(schema):
    schema["description"] = "A newer wording of the same rules"


def _forbid_active(schema):
    schema["$defs"]["domain"]["properties"]["status"]["enum"] = ["retired"]


def _allow_pending(schema):
    schema["$defs"]["domain"]["properties"]["status"]["enum"].append("pending")


def test_a_new_schema_the_stored_data_satisfies_is_stored(tmp_path):
    body = _schema(_add_description)

    results, source_dir, metadata = _download_with(
        tmp_path, {IANA_TLDS_SCHEMA_URL: body}
    )

    assert results["IANA_TLDS_SCHEMA"] == "downloaded"
    assert (source_dir / "iana-tlds-schema.json").read_bytes() == body
    assert metadata["IANA_TLDS_SCHEMA"]["cache_data"]["etag"] == '"fresh"'


def test_a_new_schema_the_stored_data_breaks_is_held_back(tmp_path):
    """The stored pair is tested together, so it must never disagree."""
    results, source_dir, metadata = _download_with(
        tmp_path, {IANA_TLDS_SCHEMA_URL: _schema(_forbid_active)}
    )

    assert results["IANA_TLDS_SCHEMA"] == "invalid"
    assert (source_dir / "iana-tlds-schema.json").read_bytes() == STORED_SCHEMA
    assert (source_dir / "iana-tlds.json").read_bytes() == STORED_DATA
    # Fetched again next run, not answered 304 while the old schema is in place.
    assert "cache_data" not in metadata["IANA_TLDS_SCHEMA"]
    assert _stored_names(source_dir) == PAIR


def test_new_data_is_checked_against_the_schema_fetched_in_the_same_run(tmp_path):
    """A value only the new schema allows is accepted when both arrive together."""

    def pending(document):
        document["domains"][0]["status"] = "pending"

    results, source_dir, _ = _download_with(
        tmp_path,
        {IANA_TLDS_SCHEMA_URL: _schema(_allow_pending), IANA_TLDS_URL: _data(pending)},
    )

    # The schema allows it; the build's parser does not know the status yet.
    assert results["IANA_TLDS_SCHEMA"] == "downloaded"
    assert results["IANA_TLDS"] == "invalid"
    assert (source_dir / "iana-tlds.json").read_bytes() == STORED_DATA


def test_rejected_data_does_not_take_a_good_new_schema_down_with_it(tmp_path):
    body = _schema(_add_description)

    results, source_dir, _ = _download_with(
        tmp_path, {IANA_TLDS_URL: b"nope", IANA_TLDS_SCHEMA_URL: body}
    )

    assert results["IANA_TLDS"] == "invalid"
    assert results["IANA_TLDS_SCHEMA"] == "downloaded"
    assert (source_dir / "iana-tlds-schema.json").read_bytes() == body
    assert (source_dir / "iana-tlds.json").read_bytes() == STORED_DATA


def test_a_first_download_stores_the_schema_then_the_data(tmp_path):
    results, source_dir, _ = _download_with(
        tmp_path,
        {IANA_TLDS_SCHEMA_URL: STORED_SCHEMA, IANA_TLDS_URL: STORED_DATA},
        stored={},
    )

    assert results["IANA_TLDS_SCHEMA"] == "downloaded"
    assert results["IANA_TLDS"] == "downloaded"
    assert _stored_names(source_dir) == PAIR


def test_a_first_schema_the_stored_data_breaks_is_removed_again(tmp_path):
    """With no earlier schema to restore, holding back means storing none."""
    results, source_dir, _ = _download_with(
        tmp_path,
        {IANA_TLDS_SCHEMA_URL: _schema(_forbid_active)},
        stored={"iana-tlds.json": STORED_DATA},
    )

    assert results["IANA_TLDS_SCHEMA"] == "invalid"
    assert _stored_names(source_dir) == ["iana-tlds.json"]
