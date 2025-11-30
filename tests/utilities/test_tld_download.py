"""Tests for TLD page download utilities (TDD)."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from src.parse import extract_main_content
from src.utilities.download import download_tld_pages
from src.utilities.urls import get_tld_file_path, get_tld_page_url

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "tlds" / "html-full"


@pytest.fixture(autouse=True)
def isolate_metadata(tmp_path):
    """Ensure all tests use isolated metadata file to prevent leaking to real metadata.json."""
    metadata_file = tmp_path / "metadata.json"
    with patch("src.utilities.metadata.METADATA_FILE", str(metadata_file)):
        yield metadata_file


def test_get_tld_page_url_regular_tld():
    """Test URL generation for regular TLD."""
    url = get_tld_page_url("com")
    assert url == "https://www.iana.org/domains/root/db/com.html"


def test_get_tld_page_url_idn_tld():
    """Test URL generation for IDN TLD."""
    url = get_tld_page_url("xn--2scrj9c")
    assert url == "https://www.iana.org/domains/root/db/xn--2scrj9c.html"


def test_get_tld_page_url_single_letter():
    """Test URL generation for single letter TLD."""
    url = get_tld_page_url("a")
    assert url == "https://www.iana.org/domains/root/db/a.html"


def test_get_tld_file_path_regular_tld(tmp_path):
    """Test file path generation for regular TLD."""
    path = get_tld_file_path("com", tmp_path)
    assert path == tmp_path / "c" / "com.html"


def test_get_tld_file_path_idn_tld(tmp_path):
    """Test file path generation for IDN TLD."""
    path = get_tld_file_path("xn--2scrj9c", tmp_path)
    assert path == tmp_path / "idn" / "xn--2scrj9c.html"


def test_get_tld_file_path_starting_with_number(tmp_path):
    """Test file path generation for TLD starting with number."""
    # Some test TLDs start with numbers
    path = get_tld_file_path("0emm", tmp_path)
    assert path == tmp_path / "0" / "0emm.html"


def test_extract_main_content_from_fixture():
    """Test extracting main content from real IANA HTML fixture."""
    # Load a fixture file
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()

    # Extract main content
    main_content = extract_main_content(full_html)

    # Should start with <main> and end with </main>
    assert main_content.startswith("<main>")
    assert main_content.endswith("</main>")

    # Should not contain header/footer elements
    assert "<header>" not in main_content
    assert "<footer>" not in main_content
    assert 'id="header"' not in main_content

    # Should contain the TLD delegation data
    assert "Delegation Record for .COM" in main_content
    assert "Sponsoring Organisation" in main_content


def test_extract_main_content_from_idn_fixture():
    """Test extracting main content from IDN TLD fixture."""
    fixture_file = FIXTURES_DIR / "idn" / "xn--2scrj9c.html"
    full_html = fixture_file.read_text()

    main_content = extract_main_content(full_html)

    assert main_content.startswith("<main>")
    assert main_content.endswith("</main>")
    assert "Delegation Record" in main_content


def test_extract_main_content_handles_no_main_tag():
    """Test extracting main content when no <main> tag exists."""
    html_without_main = "<html><body><p>No main tag</p></body></html>"

    main_content = extract_main_content(html_without_main)

    # Should return empty string when no main tag found
    assert main_content == ""


def test_extract_main_content_handles_malformed_html():
    """Test extracting main content from malformed HTML."""
    malformed_html = "<main>Unclosed main tag<p>Content"

    # Should handle gracefully without crashing
    main_content = extract_main_content(malformed_html)

    # Should return something (HTMLParser is lenient)
    assert isinstance(main_content, str)


def test_download_tld_pages_single_tld(tmp_path):
    """Test downloading a single TLD page."""
    # Load fixture data
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()

    # Mock HTTP response
    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["com"], base_dir=tmp_path)

        # Should return success
        assert results["com"] == "downloaded"

        # File should be created in correct location
        expected_path = tmp_path / "c" / "com.html"
        assert expected_path.exists()

        # Should contain main content only (not full HTML)
        saved_content = expected_path.read_text()
        assert saved_content.startswith("<main>")
        assert "<header>" not in saved_content


def test_download_tld_pages_idn_tld(tmp_path):
    """Test downloading an IDN TLD page to idn/ directory."""
    fixture_file = FIXTURES_DIR / "idn" / "xn--2scrj9c.html"
    full_html = fixture_file.read_text()

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["xn--2scrj9c"], base_dir=tmp_path)

        assert results["xn--2scrj9c"] == "downloaded"

        # Should be in idn/ directory
        expected_path = tmp_path / "idn" / "xn--2scrj9c.html"
        assert expected_path.exists()


def test_download_tld_pages_multiple_tlds(tmp_path):
    """Test downloading multiple TLD pages."""
    fixtures = {
        "com": FIXTURES_DIR / "c" / "com.html",
        "io": FIXTURES_DIR / "i" / "io.html",
        "aero": FIXTURES_DIR / "a" / "aero.html",
    }

    def mock_get(url, headers=None):
        # Extract TLD from URL
        tld = url.split("/")[-1].replace(".html", "")
        fixture_file = fixtures[tld]
        full_html = fixture_file.read_text()

        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["com", "io", "aero"], base_dir=tmp_path)

        # All should succeed
        assert results["com"] == "downloaded"
        assert results["io"] == "downloaded"
        assert results["aero"] == "downloaded"

        # Files should exist in correct directories
        assert (tmp_path / "c" / "com.html").exists()
        assert (tmp_path / "i" / "io.html").exists()
        assert (tmp_path / "a" / "aero.html").exists()


def test_download_tld_pages_handles_404(tmp_path):
    """Test handling of 404 Not Found."""
    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 404
        response.text = "Not Found"
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["nonexistent"], base_dir=tmp_path)

        # Should return error status
        assert results["nonexistent"] == "error"

        # File should not be created
        assert not (tmp_path / "n" / "nonexistent.html").exists()


def test_download_tld_pages_handles_network_error(tmp_path):
    """Test handling of network errors after retries exhausted."""
    call_count = 0

    def mock_get(url, headers=None):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Connection failed")

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["com"], base_dir=tmp_path)

        # Should return error status after retries
        assert results["com"] == "error"

        # Should have retried 3 times
        assert call_count == 3

        # File should not be created
        assert not (tmp_path / "c" / "com.html").exists()


def test_download_tld_pages_retries_on_timeout(tmp_path):
    """Test that download retries on timeout errors."""
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()
    call_count = 0

    def mock_get(url, headers=None):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TimeoutException("Request timed out")
        # Succeed on third attempt
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["com"], base_dir=tmp_path)

        # Should succeed after retries
        assert results["com"] == "downloaded"
        assert call_count == 3

        # File should exist
        assert (tmp_path / "c" / "com.html").exists()


def test_download_tld_pages_retries_on_server_error(tmp_path):
    """Test that download retries on 5xx server errors."""
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()
    call_count = 0

    def mock_get(url, headers=None):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            # Return 503 Service Unavailable
            response = Mock(spec=httpx.Response)
            response.status_code = 503
            response.text = "Service Unavailable"
            return response
        # Succeed on second attempt
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["com"], base_dir=tmp_path)

        # Should succeed after retry
        assert results["com"] == "downloaded"
        assert call_count == 2


def test_download_tld_pages_no_retry_on_client_error(tmp_path):
    """Test that download does not retry on 4xx client errors."""
    call_count = 0

    def mock_get(url, headers=None):
        nonlocal call_count
        call_count += 1
        response = Mock(spec=httpx.Response)
        response.status_code = 404
        response.text = "Not Found"
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["com"], base_dir=tmp_path)

        # Should return error without retrying
        assert results["com"] == "error"
        assert call_count == 1  # No retries for 4xx


def test_download_tld_pages_creates_directories(tmp_path):
    """Test that download creates necessary subdirectories."""
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        # tmp_path exists but c/ subdirectory doesn't
        assert not (tmp_path / "c").exists()

        download_tld_pages(["com"], base_dir=tmp_path)

        # Should create c/ directory
        assert (tmp_path / "c").exists()
        assert (tmp_path / "c" / "com.html").exists()


def test_download_tld_pages_falls_back_to_full_html_on_parse_failure(tmp_path):
    """Test that download falls back to saving full HTML if main content extraction fails."""
    # Create HTML without a <main> tag
    html_without_main = """
    <html>
    <head><title>Test TLD</title></head>
    <body>
        <header>Header content</header>
        <div>Some content but no main tag</div>
        <footer>Footer content</footer>
    </body>
    </html>
    """

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = html_without_main
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["com"], base_dir=tmp_path)

        # Should still be downloaded (fallback)
        assert results["com"] == "downloaded"

        # Should NOT save the regular file
        regular_path = tmp_path / "c" / "com.html"
        assert not regular_path.exists()

        # Should save full HTML fallback
        fallback_path = tmp_path / "c" / "com-full.html"
        assert fallback_path.exists()

        # Content should be the full HTML
        saved_content = fallback_path.read_text()
        assert saved_content == html_without_main


def test_download_tld_pages_fallback_logs_warning(tmp_path, caplog):
    """Test that fallback to full HTML logs a warning."""
    import logging

    html_without_main = "<html><body>No main tag</body></html>"

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = html_without_main
        return response

    with (
        patch("httpx.Client") as mock_client,
        caplog.at_level(logging.WARNING),
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        download_tld_pages(["com"], base_dir=tmp_path)

        # Should log a warning about fallback
        assert any("fallback" in record.message.lower() for record in caplog.records)


def test_download_tld_pages_prefers_main_content_over_fallback(tmp_path):
    """Test that download uses main content when available, not fallback."""
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["com"], base_dir=tmp_path)

        assert results["com"] == "downloaded"

        # Should save extracted main content
        regular_path = tmp_path / "c" / "com.html"
        assert regular_path.exists()

        # Should NOT save fallback
        fallback_path = tmp_path / "c" / "com-full.html"
        assert not fallback_path.exists()

        # Content should be just main tag
        saved_content = regular_path.read_text()
        assert saved_content.startswith("<main>")
        assert saved_content.endswith("</main>")


def test_download_tld_pages_handles_file_write_error(tmp_path):
    """Test handling of file write errors."""
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    # Make directory read-only to cause write error
    test_dir = tmp_path / "c"
    test_dir.mkdir(parents=True)
    test_dir.chmod(0o444)

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(["com"], base_dir=tmp_path)

        # Should return error status
        assert results["com"] == "error"

    # Cleanup: restore permissions
    test_dir.chmod(0o755)


def test_download_tld_pages_handles_empty_tld_list(tmp_path):
    """Test handling when TLD source file returns empty list."""
    with patch("src.utilities.download.parse_tlds_txt", return_value=[]):
        results = download_tld_pages(base_dir=tmp_path)

        # Should return empty dict when no TLDs found
        assert results == {}


def test_download_tld_pages_uses_default_from_source(tmp_path):
    """Test downloading all TLDs from source file when no list provided."""
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    with (
        patch("httpx.Client") as mock_client,
        patch("src.utilities.download.parse_tlds_txt", return_value=["com", "net"]),
    ):
        mock_client.return_value.__enter__.return_value.get = mock_get

        results = download_tld_pages(base_dir=tmp_path)

        # Should download both TLDs from the source
        assert "com" in results
        assert "net" in results


def test_download_tld_pages_creates_metadata_entry(tmp_path, isolate_metadata):
    """Test that download creates TLD_HTML metadata entry on first run."""
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        # First download
        results = download_tld_pages(["com"], base_dir=tmp_path)

        assert results["com"] == "downloaded"

        # Check metadata was created
        assert isolate_metadata.exists()
        with open(isolate_metadata) as f:
            metadata = json.load(f)

        assert "TLD_HTML" in metadata
        assert "last_checked" in metadata["TLD_HTML"]


def test_download_tld_pages_updates_metadata_entry(tmp_path, isolate_metadata):
    """Test that download updates existing TLD_HTML metadata entry."""
    fixture_file = FIXTURES_DIR / "c" / "com.html"
    full_html = fixture_file.read_text()

    def mock_get(url, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.text = full_html
        return response

    # Create initial metadata
    initial_metadata = {
        "TLD_HTML": {
            "last_checked": "2025-01-01T00:00:00Z",
        }
    }
    with open(isolate_metadata, "w") as f:
        json.dump(initial_metadata, f)

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get = mock_get

        # Second download
        results = download_tld_pages(["com", "net"], base_dir=tmp_path)

        assert results["com"] == "downloaded"
        assert results["net"] == "downloaded"

        # Check metadata was updated
        with open(isolate_metadata) as f:
            metadata = json.load(f)

        assert metadata["TLD_HTML"]["last_checked"] != "2025-01-01T00:00:00Z"
