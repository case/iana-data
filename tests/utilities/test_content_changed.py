"""Tests for content change detection utilities."""

import json
import shutil
import stat
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


def test_write_json_if_changed_detects_key_reorder(tmp_path):
    """A change in dict insertion order must trigger a rewrite even though
    parsed-dict equality would consider the data unchanged."""
    filepath = tmp_path / "reorder.json"
    filepath.write_text('{\n  "a": 1,\n  "b": 2\n}\n')

    reordered = {"b": 2, "a": 1}

    changed, status = write_json_if_changed(filepath, reordered)

    assert changed is True
    assert status == "written"
    assert filepath.read_text().splitlines()[1].strip().startswith('"b"')


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
    """Atomic rename failure on a new file surfaces (False, 'error')."""
    filepath = tmp_path / "new-file.json"
    data = json.loads((FIXTURES_DIR / "rdap.json").read_text())

    def mock_replace(*_args):
        raise PermissionError("Cannot rename file")

    monkeypatch.setattr("os.replace", mock_replace)

    changed, status = write_json_if_changed(filepath, data)

    assert changed is False
    assert status == "error"
    assert not filepath.exists()


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


def test_write_json_if_changed_handles_read_error_then_write_error(
    tmp_path, monkeypatch
):
    """Read fails AND the subsequent atomic rename also fails -> (False, 'error')."""
    filepath = tmp_path / "existing.json"
    filepath.write_text("{ invalid json }")

    data = json.loads((FIXTURES_DIR / "rdap.json").read_text())

    def mock_replace(*_args):
        raise PermissionError("Cannot rename file")

    monkeypatch.setattr("os.replace", mock_replace)

    changed, status = write_json_if_changed(filepath, data)

    assert changed is False
    assert status == "error"


def test_write_json_if_changed_handles_write_error_on_update(tmp_path, monkeypatch):
    """When the file exists and content changed but rename fails -> (False, 'error')."""
    filepath = tmp_path / "existing.json"
    shutil.copy(FIXTURES_DIR / "rdap.json", filepath)

    new_data = json.loads((FIXTURES_DIR / "rdap-new-content.json").read_text())

    def mock_replace(*_args):
        raise PermissionError("Cannot rename file")

    monkeypatch.setattr("os.replace", mock_replace)

    changed, status = write_json_if_changed(filepath, new_data)

    assert changed is False
    assert status == "error"


def test_atomic_write_leaves_no_temp_file_on_success(tmp_path):
    """A successful write leaves no .tmp sibling files behind."""
    filepath = tmp_path / "new-file.json"
    data = json.loads((FIXTURES_DIR / "rdap.json").read_text())

    write_json_if_changed(filepath, data)

    temp_files = [p for p in tmp_path.iterdir() if p.name != "new-file.json"]
    assert temp_files == [], f"Unexpected leftover files: {temp_files}"


def test_atomic_write_uses_0o644_permissions(tmp_path):
    """The written file has 0o644 (world-readable), not NamedTemporaryFile's 0o600.

    Without an explicit chmod, NamedTemporaryFile's secure-by-default 0o600
    mode would survive os.replace and downgrade every generated file to
    owner-only-readable. Generated artifacts are consumed by CDNs and
    other processes; 0o644 is the umask-default expectation.
    """
    filepath = tmp_path / "new-file.json"
    data = json.loads((FIXTURES_DIR / "rdap.json").read_text())

    write_json_if_changed(filepath, data)

    mode = stat.S_IMODE(filepath.stat().st_mode)
    assert mode == 0o644, f"Expected 0o644, got {oct(mode)}"


def test_atomic_write_preserves_original_when_update_fails(tmp_path, monkeypatch):
    """If the atomic rename fails, the target file stays byte-identical.

    Verifies the central guarantee of the temp-write-plus-replace pattern:
    when the rename fails, the original target is never modified, and the
    temp file is cleaned up so no .tmp sibling lingers.
    """
    filepath = tmp_path / "existing.json"
    shutil.copy(FIXTURES_DIR / "rdap.json", filepath)
    original_bytes = filepath.read_bytes()
    new_data = json.loads((FIXTURES_DIR / "rdap-new-content.json").read_text())

    def mock_replace(*_args):
        raise OSError("Disk full")

    monkeypatch.setattr("os.replace", mock_replace)

    changed, status = write_json_if_changed(filepath, new_data)

    assert changed is False
    assert status == "error"
    assert filepath.read_bytes() == original_bytes, (
        "Original file was modified despite rename failure"
    )
    temp_files = [p for p in tmp_path.iterdir() if p.name.startswith("existing.json.")]
    assert temp_files == [], f"Temp file lingered after failure: {temp_files}"
