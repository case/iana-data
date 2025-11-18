"""Tests for root zone database HTML analysis."""

from pathlib import Path

from src.analyze.root_db_html import analyze_root_db_html

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source"


def test_analyze_root_db_html_success():
    """Test that analyze_root_db_html returns success exit code for valid file."""
    fixture_path = FIXTURES_DIR / "root.html"

    exit_code = analyze_root_db_html(fixture_path)

    assert exit_code == 0


def test_analyze_root_db_html_missing_file():
    """Test that analyze_root_db_html returns error exit code for missing file."""
    nonexistent_path = FIXTURES_DIR / "does-not-exist.html"

    exit_code = analyze_root_db_html(nonexistent_path)

    assert exit_code == 1
