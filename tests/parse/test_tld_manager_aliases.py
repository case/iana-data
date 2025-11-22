"""Tests for TLD manager aliases parsing."""

from pathlib import Path

from src.parse.tld_manager_aliases import parse_tld_manager_aliases

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "manual"


def test_parse_tld_manager_aliases_returns_lookup():
    """Test that parse_tld_manager_aliases returns reverse lookup map."""
    fixture_path = FIXTURES_DIR / "tld-manager-aliases.json"

    aliases_lookup = parse_tld_manager_aliases(fixture_path)

    # Should return a dict
    assert isinstance(aliases_lookup, dict)

    # Should have 5 entries from fixture (2 + 1 + 2)
    assert len(aliases_lookup) == 5


def test_parse_tld_manager_aliases_structure():
    """Test that parse_tld_manager_aliases returns correct reverse mapping."""
    fixture_path = FIXTURES_DIR / "tld-manager-aliases.json"

    aliases_lookup = parse_tld_manager_aliases(fixture_path)

    # Check Identity Digital entries
    assert aliases_lookup["Binky Moon, LLC"] == "Identity Digital"
    assert aliases_lookup["Dog Beach, LLC"] == "Identity Digital"

    # Check Google entry
    assert aliases_lookup["Charleston Road Registry Inc."] == "Google"

    # Check VeriSign entries
    assert aliases_lookup["VeriSign Global Registry Services"] == "VeriSign"
    assert aliases_lookup["VeriSign, Inc."] == "VeriSign"


def test_parse_tld_manager_aliases_all_managers():
    """Test that parse_tld_manager_aliases includes all manager names from fixture."""
    fixture_path = FIXTURES_DIR / "tld-manager-aliases.json"

    aliases_lookup = parse_tld_manager_aliases(fixture_path)

    # All manager names from fixture should be present as keys
    expected_managers = [
        "Binky Moon, LLC",
        "Dog Beach, LLC",
        "Charleston Road Registry Inc.",
        "VeriSign Global Registry Services",
        "VeriSign, Inc.",
    ]
    for manager in expected_managers:
        assert manager in aliases_lookup


def test_parse_tld_manager_aliases_missing_file():
    """Test that parse_tld_manager_aliases returns empty dict for missing file."""
    nonexistent_path = FIXTURES_DIR / "does-not-exist.json"

    aliases_lookup = parse_tld_manager_aliases(nonexistent_path)

    # Should return empty dict, not error
    assert aliases_lookup == {}


def test_parse_tld_manager_aliases_default_path():
    """Test that parse_tld_manager_aliases can use default path."""
    # This will look in data/manual/tld-manager-aliases.json
    aliases_lookup = parse_tld_manager_aliases()

    # Should return dict (may be empty if file doesn't exist, or populated if it does)
    assert isinstance(aliases_lookup, dict)

    # If file exists, should have actual data
    if aliases_lookup:
        # Check structure - values should be strings (alias names)
        first_manager = list(aliases_lookup.keys())[0]
        assert isinstance(aliases_lookup[first_manager], str)
