"""Tests for Root Zone Database HTML content change detection."""

from pathlib import Path

from src.parse.root_db_html import root_db_html_content_changed

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


def test_root_db_content_unchanged_when_only_html_wrapper_changes():
    """Test that content is unchanged when only HTML wrapper changes (CSS/JS versions)."""
    baseline_file = FIXTURES_DIR / "root-baseline.html"
    timestamp_only_content = (FIXTURES_DIR / "root-timestamp-only.html").read_text()

    assert root_db_html_content_changed(baseline_file, timestamp_only_content) is False


def test_root_db_content_changed_when_tld_table_differs():
    """Test that content is detected as changed when TLD table entries differ."""
    baseline_file = FIXTURES_DIR / "root-baseline.html"
    new_content = (FIXTURES_DIR / "root-new-content.html").read_text()

    assert root_db_html_content_changed(baseline_file, new_content) is True


def test_root_db_content_changed_when_file_does_not_exist(tmp_path):
    """Test that content is considered changed when existing file doesn't exist."""
    non_existent_file = tmp_path / "does-not-exist.html"
    new_content = (FIXTURES_DIR / "root-baseline.html").read_text()

    assert root_db_html_content_changed(non_existent_file, new_content) is True


def test_root_db_content_changed_with_invalid_html_in_new_content():
    """Test handling of invalid HTML in new content (no table)."""
    baseline_file = FIXTURES_DIR / "root-baseline.html"
    invalid_html = "<html><body><p>No table here</p></body></html>"

    # Should return True (consider as changed) when new content has no table
    assert root_db_html_content_changed(baseline_file, invalid_html) is True


def test_root_db_content_changed_with_invalid_html_in_existing_file(tmp_path):
    """Test handling of invalid HTML in existing file (no table)."""
    # Write HTML without table
    invalid_file = tmp_path / "invalid.html"
    invalid_file.write_text("<html><body><p>No table</p></body></html>")

    new_content = (FIXTURES_DIR / "root-baseline.html").read_text()

    # Should return True (consider as changed) when existing file has no table
    assert root_db_html_content_changed(invalid_file, new_content) is True


def test_root_db_content_changed_handles_parse_exception(tmp_path, monkeypatch):
    """Test error handling when parsing new HTML content raises exception."""
    baseline_file = FIXTURES_DIR / "root-baseline.html"
    new_content = (FIXTURES_DIR / "root-new-content.html").read_text()

    # Mock RootDBHTMLParser to raise exception when parsing
    from src.parse import root_db_html

    class FailingParser:
        def feed(self, content):
            raise ValueError("Parse error")

    monkeypatch.setattr(root_db_html, "RootDBHTMLParser", lambda: FailingParser())

    # Should return True (consider as changed) when parse raises exception
    assert root_db_html_content_changed(baseline_file, new_content) is True


def test_root_db_content_changed_handles_file_read_error(tmp_path, monkeypatch):
    """Test error handling when existing file cannot be read."""
    existing_file = tmp_path / "unreadable.html"
    existing_file.write_text((FIXTURES_DIR / "root-baseline.html").read_text())

    # Make file unreadable by mocking Path.read_text
    from pathlib import Path
    original_read_text = Path.read_text

    def mock_read_text(self, *args, **kwargs):
        if "unreadable.html" in str(self):
            raise OSError("Permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mock_read_text)

    new_content = (FIXTURES_DIR / "root-new-content.html").read_text()

    # Should return True (consider as changed) when existing file can't be read
    assert root_db_html_content_changed(existing_file, new_content) is True
