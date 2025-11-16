"""Tests for TLD file analysis."""

from pathlib import Path

from src.analyze.tlds_txt import get_tlds_analysis

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source"


def test_get_tlds_analysis_baseline():
    """Test that get_tlds_analysis correctly counts TLDs and IDNs from baseline fixture."""
    fixture_path = FIXTURES_DIR / "tlds.txt"

    results = get_tlds_analysis(fixture_path)

    assert results["total"] == 22
    assert results["idns"] == 5


def test_get_tlds_analysis_timestamp_only():
    """Test analysis with timestamp-only change fixture."""
    fixture_path = FIXTURES_DIR / "tlds-timestamp-only.txt"

    results = get_tlds_analysis(fixture_path)

    # Should have same counts as baseline
    assert results["total"] == 22
    assert results["idns"] == 5


def test_get_tlds_analysis_new_content():
    """Test analysis with fixture that has additional content."""
    fixture_path = FIXTURES_DIR / "tlds-new-content.txt"

    results = get_tlds_analysis(fixture_path)

    # Should have one more TLD than baseline (22 + 1 = 23)
    assert results["total"] == 23
    # Same number of IDNs (HELLO is not an IDN)
    assert results["idns"] == 5
