"""Tests for orgs.tech aliases parsing."""

from pathlib import Path

from src.parse.tech_aliases import parse_tech_aliases

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "manual"


def test_parse_tech_aliases_returns_lookup():
    """Test that parse_tech_aliases returns reverse lookup map."""
    fixture_path = FIXTURES_DIR / "tech-aliases.json"

    aliases_lookup = parse_tech_aliases(fixture_path)

    # Should return a dict
    assert isinstance(aliases_lookup, dict)

    # Should have 7 entries from fixture (3 + 2 + 2)
    assert len(aliases_lookup) == 7


def test_parse_tech_aliases_structure():
    """Test that parse_tech_aliases returns correct reverse mapping."""
    fixture_path = FIXTURES_DIR / "tech-aliases.json"

    aliases_lookup = parse_tech_aliases(fixture_path)

    # Check Identity Digital entries
    assert aliases_lookup["Identity Digital Limited"] == "Identity Digital"
    assert aliases_lookup["Identity Digital Inc."] == "Identity Digital"
    assert aliases_lookup["Afilias"] == "Identity Digital"

    # Check Google entries
    assert aliases_lookup["Google Inc."] == "Google"
    assert aliases_lookup["Google Inc"] == "Google"

    # Check NIXI entries
    assert aliases_lookup["National Internet Exchange of India"] == "NIXI"
    assert aliases_lookup["National Internet eXchange of India"] == "NIXI"


def test_parse_tech_aliases_all_names():
    """Test that parse_tech_aliases includes all raw names from fixture."""
    fixture_path = FIXTURES_DIR / "tech-aliases.json"

    aliases_lookup = parse_tech_aliases(fixture_path)

    expected_names = [
        "Identity Digital Limited",
        "Identity Digital Inc.",
        "Afilias",
        "Google Inc.",
        "Google Inc",
        "National Internet Exchange of India",
        "National Internet eXchange of India",
    ]
    for name in expected_names:
        assert name in aliases_lookup


def test_parse_tech_aliases_missing_file():
    """Test that parse_tech_aliases returns empty dict for missing file."""
    nonexistent_path = FIXTURES_DIR / "does-not-exist.json"

    aliases_lookup = parse_tech_aliases(nonexistent_path)

    # Should return empty dict, not error
    assert aliases_lookup == {}


def test_parse_tech_aliases_default_path():
    """Test that parse_tech_aliases can use default path."""
    # This will look in data/manual/tech-aliases.json
    aliases_lookup = parse_tech_aliases()

    # Should return dict (may be empty if file doesn't exist, or populated if it does)
    assert isinstance(aliases_lookup, dict)

    # If file exists, values should be canonical alias strings
    if aliases_lookup:
        first_name = next(iter(aliases_lookup))
        assert isinstance(aliases_lookup[first_name], str)
