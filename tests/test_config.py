"""Tests for configuration module."""

import logging

from src.config import (
    GENERATED_DIR,
    IANA_URLS,
    SOURCE_DIR,
    SOURCE_FILES,
    TLDS_OUTPUT_FILE,
    setup_logging,
)


def test_iana_urls_defined():
    """Test that IANA URLs are properly defined."""
    assert "RDAP_BOOTSTRAP" in IANA_URLS
    assert "TLD_LIST" in IANA_URLS
    assert "IANA_TLDS" in IANA_URLS
    assert "IANA_TLDS_SCHEMA" in IANA_URLS
    assert "ROOT_ZONE_DB" not in IANA_URLS

    # Verify URLs are strings and look valid
    assert IANA_URLS["RDAP_BOOTSTRAP"].startswith("https://")
    assert IANA_URLS["TLD_LIST"].startswith("https://")
    assert IANA_URLS["IANA_TLDS"] == "https://data.iana.org/TLD/v1/tlds.json"
    assert IANA_URLS["IANA_TLDS_SCHEMA"] == (
        "https://data.iana.org/TLD/v1/tlds-schema.json"
    )


def test_source_files_defined():
    """Test that source file names are properly defined."""
    assert "RDAP_BOOTSTRAP" in SOURCE_FILES
    assert "TLD_LIST" in SOURCE_FILES
    assert "ROOT_ZONE_DB" not in SOURCE_FILES

    # Verify file names are strings
    assert isinstance(SOURCE_FILES["RDAP_BOOTSTRAP"], str)
    assert isinstance(SOURCE_FILES["TLD_LIST"], str)
    assert SOURCE_FILES["IANA_TLDS"] == "iana-tlds.json"
    assert SOURCE_FILES["IANA_TLDS_SCHEMA"] == "iana-tlds-schema.json"


def test_every_downloaded_iana_source_has_a_file_name():
    """The downloader indexes SOURCE_FILES by every IANA_URLS key."""
    assert set(IANA_URLS) <= set(SOURCE_FILES)


def test_directories_defined():
    """Test that directories are properly defined."""
    assert isinstance(SOURCE_DIR, str)
    assert isinstance(GENERATED_DIR, str)
    assert len(SOURCE_DIR) > 0
    assert len(GENERATED_DIR) > 0


def test_output_file_defined():
    """Test that output file path is properly defined."""
    assert isinstance(TLDS_OUTPUT_FILE, str)
    assert TLDS_OUTPUT_FILE.endswith(".json")
    assert GENERATED_DIR in TLDS_OUTPUT_FILE


def test_setup_logging():
    """Test that setup_logging configures logging without errors."""
    # Clear any existing logging configuration
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Call setup_logging
    setup_logging()

    # Verify logging is configured
    assert logger.level == logging.INFO
    assert len(logger.handlers) > 0

    # Verify handler has correct format
    handler = logger.handlers[0]
    assert handler.formatter is not None
