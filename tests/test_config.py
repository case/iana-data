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
    assert "ROOT_ZONE_DB" in IANA_URLS

    # Verify URLs are strings and look valid
    assert IANA_URLS["RDAP_BOOTSTRAP"].startswith("https://")
    assert IANA_URLS["TLD_LIST"].startswith("https://")
    assert IANA_URLS["ROOT_ZONE_DB"].startswith("https://")


def test_source_files_defined():
    """Test that source file names are properly defined."""
    assert "RDAP_BOOTSTRAP" in SOURCE_FILES
    assert "TLD_LIST" in SOURCE_FILES
    assert "ROOT_ZONE_DB" in SOURCE_FILES

    # Verify file names are strings
    assert isinstance(SOURCE_FILES["RDAP_BOOTSTRAP"], str)
    assert isinstance(SOURCE_FILES["TLD_LIST"], str)
    assert isinstance(SOURCE_FILES["ROOT_ZONE_DB"], str)


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
