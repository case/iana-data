"""Tests for supplemental ccTLD RDAP parsing."""

from pathlib import Path

from src.parse.supplemental_cctld_rdap import parse_supplemental_cctld_rdap

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "generated"


def test_parse_supplemental_cctld_rdap_returns_lookup():
    """Test that parse_supplemental_cctld_rdap returns TLD lookup map."""
    fixture_path = FIXTURES_DIR / "supplemental-cctld-rdap.json"

    rdap_lookup = parse_supplemental_cctld_rdap(fixture_path)

    # Should return a dict
    assert isinstance(rdap_lookup, dict)

    # Should have 4 entries from fixture
    assert len(rdap_lookup) == 4


def test_parse_supplemental_cctld_rdap_structure():
    """Test that parse_supplemental_cctld_rdap returns correct structure."""
    fixture_path = FIXTURES_DIR / "supplemental-cctld-rdap.json"

    rdap_lookup = parse_supplemental_cctld_rdap(fixture_path)

    # Check specific entry structure
    assert "ch" in rdap_lookup
    assert rdap_lookup["ch"]["rdap_server"] == "https://rdap.nic.ch/"
    assert rdap_lookup["ch"]["source"] == "https://www.nic.ch/whois/rdap/"


def test_parse_supplemental_cctld_rdap_all_tlds():
    """Test that parse_supplemental_cctld_rdap includes all TLDs from fixture."""
    fixture_path = FIXTURES_DIR / "supplemental-cctld-rdap.json"

    rdap_lookup = parse_supplemental_cctld_rdap(fixture_path)

    # All TLDs from fixture should be present
    assert "ch" in rdap_lookup
    assert "de" in rdap_lookup
    assert "li" in rdap_lookup
    assert "io" in rdap_lookup


def test_parse_supplemental_cctld_rdap_empty_source():
    """Test that parse_supplemental_cctld_rdap handles empty source field."""
    fixture_path = FIXTURES_DIR / "supplemental-cctld-rdap.json"

    rdap_lookup = parse_supplemental_cctld_rdap(fixture_path)

    # io has empty source in fixture
    assert "io" in rdap_lookup
    assert rdap_lookup["io"]["source"] == ""


def test_parse_supplemental_cctld_rdap_missing_file():
    """Test that parse_supplemental_cctld_rdap returns empty dict for missing file."""
    nonexistent_path = FIXTURES_DIR / "does-not-exist.json"

    rdap_lookup = parse_supplemental_cctld_rdap(nonexistent_path)

    # Should return empty dict, not error
    assert rdap_lookup == {}


def test_parse_supplemental_cctld_rdap_default_path():
    """Test that parse_supplemental_cctld_rdap can use default path."""
    # This will look in data/generated/supplemental-cctld-rdap.json
    rdap_lookup = parse_supplemental_cctld_rdap()

    # Should return dict (may be empty if file doesn't exist, or populated if it does)
    assert isinstance(rdap_lookup, dict)

    # If file exists, should have actual data
    if rdap_lookup:
        # Check structure of first entry
        first_tld = list(rdap_lookup.keys())[0]
        assert "rdap_server" in rdap_lookup[first_tld]
        assert "source" in rdap_lookup[first_tld]
