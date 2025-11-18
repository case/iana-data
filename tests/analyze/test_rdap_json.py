"""Tests for RDAP bootstrap JSON analysis."""

from pathlib import Path

from src.analyze.rdap_json import analyze_rdap_json

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source"


def test_analyze_rdap_json_success():
    """Test that analyze_rdap_json returns success exit code for valid file."""
    fixture_path = FIXTURES_DIR / "rdap.json"

    exit_code = analyze_rdap_json(fixture_path)

    assert exit_code == 0


def test_analyze_rdap_json_missing_file():
    """Test that analyze_rdap_json returns error exit code for missing file."""
    nonexistent_path = FIXTURES_DIR / "does-not-exist.json"

    exit_code = analyze_rdap_json(nonexistent_path)

    assert exit_code == 1
