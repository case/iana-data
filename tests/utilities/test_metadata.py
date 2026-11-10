"""Tests for metadata utilities."""

import json
import shutil
from pathlib import Path

import pytest

from src.utilities.metadata import (
    load_metadata,
    record_iptoasn_fetch,
    save_metadata,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "metadata"


def test_load_metadata_file_exists(tmp_path):
    """Test loading metadata from existing file."""
    # Copy fixture to temp location
    fixture_file = FIXTURES_DIR / "valid-metadata.json"
    metadata_file = tmp_path / "metadata.json"
    shutil.copy(fixture_file, metadata_file)

    import src.utilities.metadata as metadata_module

    original_file = metadata_module.METADATA_FILE
    try:
        metadata_module.METADATA_FILE = str(metadata_file)

        result = load_metadata()

        # Verify structure
        assert "RDAP_BOOTSTRAP" in result
        assert "TLD_LIST" in result
        assert "ROOT_ZONE_DB" in result

        # Verify content from fixture
        assert (
            result["RDAP_BOOTSTRAP"]["cache_data"]["etag"]
            == '"1182e-642f50662aab6-gzip"'
        )
        assert (
            result["TLD_LIST"]["cache_data"]["last_modified"]
            == "Tue, 18 Nov 2025 07:07:01 GMT"
        )
    finally:
        metadata_module.METADATA_FILE = original_file


def test_load_metadata_file_not_exists(tmp_path):
    """Test loading metadata when file doesn't exist."""
    import src.utilities.metadata as metadata_module

    original_file = metadata_module.METADATA_FILE
    try:
        metadata_module.METADATA_FILE = str(tmp_path / "does-not-exist.json")

        result = load_metadata()
        assert result == {}
    finally:
        metadata_module.METADATA_FILE = original_file


def test_load_metadata_corrupted_json(tmp_path):
    """Test loading metadata from corrupted JSON file."""
    # Copy corrupted fixture to temp location
    fixture_file = FIXTURES_DIR / "corrupted-metadata.json"
    metadata_file = tmp_path / "metadata.json"
    shutil.copy(fixture_file, metadata_file)

    import src.utilities.metadata as metadata_module

    original_file = metadata_module.METADATA_FILE
    try:
        metadata_module.METADATA_FILE = str(metadata_file)

        result = load_metadata()
        assert result == {}  # Should return empty dict on error
    finally:
        metadata_module.METADATA_FILE = original_file


def test_save_metadata_creates_directory(tmp_path):
    """Test that save_metadata creates parent directory if needed."""
    # Load test data from fixture
    fixture_file = FIXTURES_DIR / "valid-metadata.json"
    with open(fixture_file) as f:
        test_metadata = json.load(f)

    metadata_file = tmp_path / "data" / "generated" / "metadata.json"

    import src.utilities.metadata as metadata_module

    original_file = metadata_module.METADATA_FILE
    try:
        metadata_module.METADATA_FILE = str(metadata_file)

        save_metadata(test_metadata)

        # Verify directory was created
        assert metadata_file.parent.exists()

        # Verify file was created with correct content
        assert metadata_file.exists()
        with open(metadata_file) as f:
            saved = json.load(f)
        assert saved == test_metadata
    finally:
        metadata_module.METADATA_FILE = original_file


def test_save_metadata_overwrites_existing(tmp_path):
    """Test that save_metadata overwrites existing file."""
    metadata_file = tmp_path / "metadata.json"

    # Create initial metadata from one fixture
    initial_fixture = FIXTURES_DIR / "stale-cache-metadata.json"
    shutil.copy(initial_fixture, metadata_file)

    # Save new metadata from different fixture
    new_fixture = FIXTURES_DIR / "fresh-cache-metadata.json"
    with open(new_fixture) as f:
        new_metadata = json.load(f)

    import src.utilities.metadata as metadata_module

    original_file = metadata_module.METADATA_FILE
    try:
        metadata_module.METADATA_FILE = str(metadata_file)

        save_metadata(new_metadata)

        # Verify it was overwritten
        with open(metadata_file) as f:
            saved = json.load(f)
        assert saved == new_metadata
    finally:
        metadata_module.METADATA_FILE = original_file


def test_save_metadata_formatted_json(tmp_path):
    """Test that save_metadata uses indented JSON."""
    metadata_file = tmp_path / "metadata.json"

    # Load test data from fixture
    fixture_file = FIXTURES_DIR / "valid-metadata.json"
    with open(fixture_file) as f:
        test_metadata = json.load(f)

    import src.utilities.metadata as metadata_module

    original_file = metadata_module.METADATA_FILE
    try:
        metadata_module.METADATA_FILE = str(metadata_file)

        save_metadata(test_metadata)

        # Verify JSON is formatted (has newlines and indentation)
        content = metadata_file.read_text()
        assert "\n" in content
        assert "  " in content  # Should have indentation
    finally:
        metadata_module.METADATA_FILE = original_file


def test_load_save_roundtrip(tmp_path):
    """Test that save and load are compatible."""
    metadata_file = tmp_path / "metadata.json"

    # Load test data from fixture
    fixture_file = FIXTURES_DIR / "valid-metadata.json"
    with open(fixture_file) as f:
        test_metadata = json.load(f)

    import src.utilities.metadata as metadata_module

    original_file = metadata_module.METADATA_FILE
    try:
        metadata_module.METADATA_FILE = str(metadata_file)

        # Save metadata
        save_metadata(test_metadata)

        # Load it back
        loaded = load_metadata()

        # Should be identical
        assert loaded == test_metadata
    finally:
        metadata_module.METADATA_FILE = original_file


class TestRecordIptoasnFetch:
    """last_downloaded must not advance on a night the artifact went unused."""

    def _metadata(self, tmp_path, monkeypatch, existing=None):
        path = tmp_path / "metadata.json"
        if existing is not None:
            path.write_text(json.dumps(existing), encoding="utf-8")
        monkeypatch.setattr(
            "src.utilities.metadata.METADATA_FILE", str(path), raising=False
        )
        return path

    def test_a_consumed_artifact_records_all_three_fields(self, tmp_path, monkeypatch):
        path = self._metadata(tmp_path, monkeypatch, {})

        record_iptoasn_fetch(
            checked_at="2026-09-24T07:10:00Z",
            downloaded_at="2026-09-24T03:36:05Z",
            run_id="35952113913",
        )

        entry = json.loads(path.read_text())["IPTOASN"]
        assert entry["last_checked"] == "2026-09-24T07:10:00Z"
        assert entry["last_downloaded"] == "2026-09-24T03:36:05Z"
        assert entry["run_id"] == "35952113913"

    def test_an_unused_artifact_moves_only_last_checked(self, tmp_path, monkeypatch):
        """A preserve night is iptoasn's 304: the download date must not move."""
        path = self._metadata(
            tmp_path,
            monkeypatch,
            {
                "IPTOASN": {
                    "last_checked": "2026-09-20T07:00:00Z",
                    "last_downloaded": "2026-09-20T03:40:00Z",
                    "run_id": "111",
                }
            },
        )

        record_iptoasn_fetch(checked_at="2026-09-24T07:10:00Z")

        entry = json.loads(path.read_text())["IPTOASN"]
        assert entry["last_checked"] == "2026-09-24T07:10:00Z"
        assert entry["last_downloaded"] == "2026-09-20T03:40:00Z"
        assert entry["run_id"] == "111"

    def test_it_never_invents_a_download_date(self, tmp_path, monkeypatch):
        path = self._metadata(tmp_path, monkeypatch, {})

        record_iptoasn_fetch(checked_at="2026-09-24T07:10:00Z")

        entry = json.loads(path.read_text())["IPTOASN"]
        assert "last_downloaded" not in entry
        assert "run_id" not in entry

    def test_other_sources_are_untouched(self, tmp_path, monkeypatch):
        path = self._metadata(
            tmp_path,
            monkeypatch,
            {"TLD_LIST": {"last_checked": "2026-09-01T00:00:00Z", "cache_data": {}}},
        )

        record_iptoasn_fetch(checked_at="2026-09-24T07:10:00Z")

        data = json.loads(path.read_text())
        assert data["TLD_LIST"] == {
            "last_checked": "2026-09-01T00:00:00Z",
            "cache_data": {},
        }

    def test_unmanaged_keys_inside_the_entry_survive(self, tmp_path, monkeypatch):
        """Merge, not replace: an unrelated key must not be dropped."""
        path = self._metadata(
            tmp_path, monkeypatch, {"IPTOASN": {"note": "kept by hand"}}
        )

        record_iptoasn_fetch(
            checked_at="2026-09-24T07:10:00Z",
            downloaded_at="2026-09-24T03:36:05Z",
            run_id="9",
        )

        assert json.loads(path.read_text())["IPTOASN"]["note"] == "kept by hand"

    def test_a_run_id_without_a_download_date_is_refused(self, tmp_path, monkeypatch):
        """run_id describes the artifact that fed the build; alone it is a lie."""
        self._metadata(tmp_path, monkeypatch, {})

        with pytest.raises(ValueError, match="run_id"):
            record_iptoasn_fetch(checked_at="2026-09-24T07:10:00Z", run_id="9")

    def test_a_direct_download_clears_a_stale_run_id(self, tmp_path, monkeypatch):
        """Bytes from iptoasn.com are not attributable to a producer run."""
        path = self._metadata(
            tmp_path,
            monkeypatch,
            {
                "IPTOASN": {
                    "last_checked": "2026-09-20T07:00:00Z",
                    "last_downloaded": "2026-09-20T03:40:00Z",
                    "run_id": "111",
                }
            },
        )

        record_iptoasn_fetch(
            checked_at="2026-09-24T09:00:00Z", downloaded_at="2026-09-24T09:00:00Z"
        )

        entry = json.loads(path.read_text())["IPTOASN"]
        assert entry["last_downloaded"] == "2026-09-24T09:00:00Z"
        assert "run_id" not in entry

    def test_an_unused_artifact_leaves_the_run_id_alone(self, tmp_path, monkeypatch):
        """Clearing is tied to a new download, not to every call."""
        path = self._metadata(tmp_path, monkeypatch, {"IPTOASN": {"run_id": "111"}})

        record_iptoasn_fetch(checked_at="2026-09-24T09:00:00Z")

        assert json.loads(path.read_text())["IPTOASN"]["run_id"] == "111"

    def test_a_write_that_did_not_land_raises(self, tmp_path, monkeypatch):
        """save_metadata only logs a failed write; the nightly needs a non-zero exit."""
        path = self._metadata(tmp_path, monkeypatch)
        path.mkdir()

        with pytest.raises(OSError, match="not written"):
            record_iptoasn_fetch(checked_at="2026-09-24T07:10:00Z")
