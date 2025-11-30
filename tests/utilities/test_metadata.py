"""Tests for metadata utilities."""

import json
import shutil
from pathlib import Path

from src.utilities.metadata import load_metadata, save_metadata

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
        assert result["RDAP_BOOTSTRAP"]["cache_data"]["etag"] == "\"1182e-642f50662aab6-gzip\""
        assert result["TLD_LIST"]["cache_data"]["last_modified"] == "Tue, 18 Nov 2025 07:07:01 GMT"
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
