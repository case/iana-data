"""Tests for RDAP JSON content change detection."""

from pathlib import Path

from src.parse.rdap_json import rdap_json_content_changed

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


def test_rdap_content_unchanged_when_only_timestamp_differs():
    """Test that content is unchanged when only publication timestamp differs."""
    baseline_file = FIXTURES_DIR / "rdap.json"
    timestamp_only_content = (FIXTURES_DIR / "rdap-timestamp-only.json").read_text()

    assert rdap_json_content_changed(baseline_file, timestamp_only_content) is False


def test_rdap_content_changed_when_services_differ():
    """Test that content is detected as changed when services array differs."""
    baseline_file = FIXTURES_DIR / "rdap.json"
    new_content = (FIXTURES_DIR / "rdap-new-content.json").read_text()

    assert rdap_json_content_changed(baseline_file, new_content) is True


def test_rdap_content_changed_when_file_does_not_exist(tmp_path):
    """Test that content is considered changed when existing file doesn't exist."""
    non_existent_file = tmp_path / "does-not-exist.json"
    new_content = (FIXTURES_DIR / "rdap.json").read_text()

    assert rdap_json_content_changed(non_existent_file, new_content) is True


def test_rdap_content_changed_with_invalid_json_in_new_content():
    """Test handling of invalid JSON in new content."""
    baseline_file = FIXTURES_DIR / "rdap.json"
    invalid_json = "{ invalid json here"

    # Should return True (consider as changed) when new content is invalid
    assert rdap_json_content_changed(baseline_file, invalid_json) is True


def test_rdap_content_changed_with_invalid_json_in_existing_file(tmp_path):
    """Test handling of invalid JSON in existing file."""
    # Write invalid JSON to existing file
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{ invalid json }")

    new_content = (FIXTURES_DIR / "rdap.json").read_text()

    # Should return True (consider as changed) when existing file is invalid
    assert rdap_json_content_changed(invalid_file, new_content) is True
