"""Tests for content change detection utilities."""

import json
import shutil
from pathlib import Path

from src.utilities.content_changed import write_json_if_changed

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


def test_write_json_if_changed_creates_new_file(tmp_path):
    """Test that write_json_if_changed creates file when it doesn't exist."""
    filepath = tmp_path / "new-file.json"
    # Use rdap.json fixture as test data
    data = json.loads((FIXTURES_DIR / "rdap.json").read_text())

    changed, status = write_json_if_changed(filepath, data)

    assert changed is True
    assert status == "written"
    assert filepath.exists()
    assert json.loads(filepath.read_text()) == data


def test_write_json_if_changed_updates_when_content_differs(tmp_path):
    """Test that write_json_if_changed updates file when content differs."""
    filepath = tmp_path / "existing-file.json"
    # Start with baseline rdap.json
    shutil.copy(FIXTURES_DIR / "rdap.json", filepath)

    # Load new content with different services array
    new_data = json.loads((FIXTURES_DIR / "rdap-new-content.json").read_text())

    changed, status = write_json_if_changed(
        filepath, new_data, exclude_fields=["publication"]
    )

    assert changed is True
    assert status == "written"
    assert json.loads(filepath.read_text()) == new_data


def test_write_json_if_changed_skips_when_only_excluded_fields_differ(tmp_path):
    """Test that write_json_if_changed skips write when only excluded fields differ."""
    filepath = tmp_path / "existing-file.json"
    # Start with baseline rdap.json
    shutil.copy(FIXTURES_DIR / "rdap.json", filepath)
    initial_data = json.loads(filepath.read_text())

    # Load content with only publication timestamp changed
    new_data = json.loads((FIXTURES_DIR / "rdap-timestamp-only.json").read_text())

    changed, status = write_json_if_changed(
        filepath, new_data, exclude_fields=["publication"]
    )

    assert changed is False
    assert status == "unchanged"
    # File should not be modified - still has old publication timestamp
    assert json.loads(filepath.read_text()) == initial_data


def test_write_json_if_changed_detects_array_changes(tmp_path):
    """Test that write_json_if_changed detects changes in arrays."""
    filepath = tmp_path / "existing-file.json"
    shutil.copy(FIXTURES_DIR / "rdap.json", filepath)

    # New content has additional service in services array
    new_data = json.loads((FIXTURES_DIR / "rdap-new-content.json").read_text())

    changed, status = write_json_if_changed(filepath, new_data)

    assert changed is True
    assert status == "written"


def test_write_json_if_changed_formats_json_with_indentation(tmp_path):
    """Test that write_json_if_changed formats JSON with proper indentation."""
    filepath = tmp_path / "formatted-file.json"
    data = json.loads((FIXTURES_DIR / "rdap.json").read_text())

    write_json_if_changed(filepath, data, indent=2)

    content = filepath.read_text()
    assert "\n" in content  # Should have newlines
    assert "  " in content  # Should have 2-space indentation


def test_write_json_if_changed_preserves_file_when_unchanged(tmp_path):
    """Test that file modification time is preserved when content is unchanged."""
    filepath = tmp_path / "preserved-file.json"
    shutil.copy(FIXTURES_DIR / "rdap.json", filepath)

    initial_mtime = filepath.stat().st_mtime

    # Write content with only publication changed (excluded field)
    new_data = json.loads((FIXTURES_DIR / "rdap-timestamp-only.json").read_text())
    changed, _ = write_json_if_changed(
        filepath, new_data, exclude_fields=["publication"]
    )

    assert changed is False
    # File should not be touched
    assert filepath.stat().st_mtime == initial_mtime


def test_write_json_if_changed_handles_write_error_for_new_file(tmp_path, monkeypatch):
    """Test error handling when writing a new file fails."""
    filepath = tmp_path / "new-file.json"
    data = json.loads((FIXTURES_DIR / "rdap.json").read_text())

    # Mock open to raise exception
    import builtins
    original_open = builtins.open

    def mock_open(*args, **kwargs):
        if "w" in str(kwargs.get("mode", args[1] if len(args) > 1 else "")):
            raise PermissionError("Cannot write file")
        return original_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)

    changed, status = write_json_if_changed(filepath, data)

    assert changed is False
    assert status == "error"


def test_write_json_if_changed_handles_corrupted_existing_file(tmp_path):
    """Test handling of corrupted existing file (invalid JSON)."""
    filepath = tmp_path / "corrupted.json"
    filepath.write_text("{ invalid json here }")

    new_data = json.loads((FIXTURES_DIR / "rdap.json").read_text())

    # Should overwrite corrupted file
    changed, status = write_json_if_changed(filepath, new_data)

    assert changed is True
    assert status == "written"
    # File should be valid JSON now
    assert json.loads(filepath.read_text()) == new_data


def test_write_json_if_changed_handles_read_error_then_write_error(tmp_path, monkeypatch):
    """Test error handling when reading fails AND subsequent write fails."""
    filepath = tmp_path / "existing.json"
    filepath.write_text("{ invalid json }")

    data = json.loads((FIXTURES_DIR / "rdap.json").read_text())

    # Mock open to fail on write
    import builtins
    original_open = builtins.open

    def mock_open(*args, **kwargs):
        mode = kwargs.get("mode", args[1] if len(args) > 1 else "")
        if "w" in str(mode):
            raise PermissionError("Cannot write file")
        return original_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)

    changed, status = write_json_if_changed(filepath, data)

    assert changed is False
    assert status == "error"


def test_write_json_if_changed_handles_write_error_on_update(tmp_path, monkeypatch):
    """Test error handling when writing updated content fails."""
    filepath = tmp_path / "existing.json"
    shutil.copy(FIXTURES_DIR / "rdap.json", filepath)

    new_data = json.loads((FIXTURES_DIR / "rdap-new-content.json").read_text())

    # Mock open to fail only on the write after successful read
    import builtins
    original_open = builtins.open
    call_count = [0]

    def mock_open(*args, **kwargs):
        mode = kwargs.get("mode", args[1] if len(args) > 1 else "")
        if "w" in str(mode):
            call_count[0] += 1
            # Fail on write (first write attempt after read)
            raise PermissionError("Cannot write file")
        return original_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)

    changed, status = write_json_if_changed(filepath, new_data)

    assert changed is False
    assert status == "error"
