"""Integration tests for TLD build process."""

import json
from pathlib import Path

import pytest

from src.build.tlds import build_tlds_json
from src.parse.rdap_json import parse_rdap_json
from src.parse.root_db_html import parse_root_db_html
from src.parse.tlds_txt import parse_tlds_txt

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"

@pytest.fixture
def temp_output(tmp_path, monkeypatch):
    """Fixture to redirect build output to temp directory."""
    output_file = tmp_path / "tlds.json"
    metadata_file = tmp_path / "metadata.json"
    monkeypatch.setattr("src.build.tlds.TLDS_OUTPUT_FILE", str(output_file))
    monkeypatch.setattr("src.utilities.metadata.METADATA_FILE", str(metadata_file))
    return output_file

def test_build_tlds_json_creates_file(temp_output):
    """Test that build_tlds_json creates the output file."""
    result = build_tlds_json()

    # Should return result dict
    assert "total_tlds" in result
    assert "output_file" in result

    # Should create output file
    assert temp_output.exists()

def test_build_tlds_json_has_correct_structure(temp_output):
    """Test that generated tlds.json has correct top-level structure."""
    build_tlds_json()

    with open(temp_output) as f:
        data = json.load(f)

    # Check top-level fields
    assert "description" in data
    assert "publication" in data
    assert "sources" in data
    assert "tlds" in data

    # Check sources structure
    assert "iana_root_db" in data["sources"]
    assert "iana_rdap" in data["sources"]

    # Check tlds is a list
    assert isinstance(data["tlds"], list)

def test_build_tlds_json_tld_count_matches_source(temp_output):
    """Test that number of TLDs in output matches root zone source."""
    # Parse root zone to get expected count
    root_zone_entries = parse_root_db_html()
    expected_count = len(root_zone_entries)

    # Build and check output
    result = build_tlds_json()

    assert result["total_tlds"] == expected_count

    # Also verify in the file itself
    
    with open(temp_output) as f:
        data = json.load(f)

    assert len(data["tlds"]) == expected_count

def test_build_tlds_json_has_required_fields(temp_output):
    """Test that each TLD entry has required fields."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    # Check first few entries have required fields
    for tld_entry in data["tlds"][:10]:
        assert "tld" in tld_entry
        assert "delegated" in tld_entry
        assert "iana_tag" in tld_entry
        assert "type" in tld_entry
        # tld_manager is now in orgs object, which is optional for undelegated TLDs

def test_build_tlds_json_strips_leading_dots(temp_output):
    """Test that TLDs in output don't have leading dots."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    # Check that no TLD starts with a dot
    for tld_entry in data["tlds"]:
        assert not tld_entry["tld"].startswith(".")

def test_build_tlds_json_derives_type_correctly(temp_output):
    """Test that type field is correctly derived from iana_tag."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    for tld_entry in data["tlds"]:
        iana_tag = tld_entry["iana_tag"]
        derived_type = tld_entry["type"]

        # Check derivation logic
        if iana_tag == "country-code":
            assert derived_type == "cctld"
        else:
            assert derived_type == "gtld"

def test_build_tlds_json_delegated_status(temp_output):
    """Test that delegated status is correctly set."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    for tld_entry in data["tlds"]:
        delegated = tld_entry["delegated"]

        # Check logic: delegated TLDs should have orgs with tld_manager
        if delegated:
            assert "orgs" in tld_entry
            assert "tld_manager" in tld_entry["orgs"]
        # Undelegated TLDs may or may not have orgs

def test_build_tlds_json_rdap_servers_present(temp_output):
    """Test that RDAP servers are included for TLDs that have them."""
    # Get RDAP lookup to know which TLDs should have servers
    rdap_lookup = parse_rdap_json()

    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    # Build a map of TLD to entry for easy lookup
    tld_map = {entry["tld"]: entry for entry in data["tlds"]}

    # Check a few TLDs that should have RDAP servers
    for tld in list(rdap_lookup.keys())[:5]:
        if tld in tld_map:
            entry = tld_map[tld]
            # RDAP server should be present (from page data or bootstrap)
            assert "rdap_server" in entry
            # Should also have rdap_source annotation
            assert "annotations" in entry
            assert "rdap_source" in entry["annotations"]

def test_build_tlds_json_idn_unicode_field(temp_output):
    """Test that IDN TLDs have tld_unicode field."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    # Find an IDN TLD (starts with xn--)
    idn_tlds = [entry for entry in data["tlds"] if entry["tld"].startswith("xn--")]

    if idn_tlds:
        # At least one IDN should have tld_unicode
        idn_with_unicode = [e for e in idn_tlds if "tld_unicode" in e]
        assert len(idn_with_unicode) > 0

        # Check that tld_unicode is different from tld
        for entry in idn_with_unicode:
            assert entry["tld_unicode"] != entry["tld"]
            # Unicode version should not start with xn--
            assert not entry["tld_unicode"].startswith("xn--")

def test_build_tlds_json_publication_timestamp_format(temp_output):
    """Test that publication timestamp uses correct format (seconds + Z)."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    publication = data["publication"]

    # Should end with Z
    assert publication.endswith("Z")

    # Should not have microseconds (no decimal point)
    assert "." not in publication

    # Should match format YYYY-MM-DDTHH:MM:SSZ
    # Length should be 20 characters
    assert len(publication) == 20

def test_build_tlds_json_delegated_count_matches_tlds_txt(temp_output):
    """Test that delegated TLD count matches all-tlds text file."""
    # Parse TLDs text file to get expected count
    tlds_txt_list = parse_tlds_txt()
    expected_delegated_count = len(tlds_txt_list)

    # Build and check output
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    # Count delegated TLDs in output
    delegated_tlds = [entry for entry in data["tlds"] if entry["delegated"]]
    actual_delegated_count = len(delegated_tlds)

    # Should match
    assert actual_delegated_count == expected_delegated_count

def test_build_tlds_json_ascii_cctld_has_country_name(temp_output):
    """Test that ASCII ccTLDs have country_name_iso in annotations."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    # Build a map of TLD to entry
    tld_map = {entry["tld"]: entry for entry in data["tlds"]}

    # Test some ASCII ccTLDs
    test_cctlds = {
        "us": "United States",
        "gb": "United Kingdom",
        "de": "Germany",
        "jp": "Japan",
        "fr": "France",
    }

    for cctld, expected_name in test_cctlds.items():
        assert cctld in tld_map
        entry = tld_map[cctld]
        assert "annotations" in entry
        assert "country_name_iso" in entry["annotations"]
        assert entry["annotations"]["country_name_iso"] == expected_name

def test_build_tlds_json_idn_cctld_has_country_name(temp_output):
    """Test that IDN ccTLDs have country_name_iso in annotations."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    # Find IDN ccTLDs (have tld_iso field)
    idn_cctlds = [entry for entry in data["tlds"] if "tld_iso" in entry]

    assert len(idn_cctlds) > 0, "Should have at least some IDN ccTLDs"

    # Check that they all have country_name_iso
    for entry in idn_cctlds:
        assert "annotations" in entry
        assert "country_name_iso" in entry["annotations"]
        # Country name should be non-empty string
        assert isinstance(entry["annotations"]["country_name_iso"], str)
        assert len(entry["annotations"]["country_name_iso"]) > 0

def test_build_tlds_json_cctld_overrides(temp_output):
    """Test that ccTLD overrides (ac, eu, su, uk) have correct country names."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    # Build a map of TLD to entry
    tld_map = {entry["tld"]: entry for entry in data["tlds"]}

    # Test overrides (not in ISO 3166-1)
    overrides = {
        "ac": "Ascension Island",
        "eu": "European Union",
        "su": "Soviet Union",
        "uk": "United Kingdom",
    }

    for cctld, expected_name in overrides.items():
        if cctld in tld_map:
            entry = tld_map[cctld]
            assert "annotations" in entry
            assert "country_name_iso" in entry["annotations"]
            assert entry["annotations"]["country_name_iso"] == expected_name

def test_build_tlds_json_gtld_no_country_name(temp_output):
    """Test that gTLDs do not have country_name_iso."""
    build_tlds_json()

    
    with open(temp_output) as f:
        data = json.load(f)

    # Find gTLDs
    gtlds = [entry for entry in data["tlds"] if entry["type"] == "gtld"]

    # Check some common gTLDs
    gtld_tlds = [e["tld"] for e in gtlds]
    test_gtlds = ["com", "org", "net", "info", "biz"]

    for gtld in test_gtlds:
        if gtld in gtld_tlds:
            entry = [e for e in gtlds if e["tld"] == gtld][0]
            # Should not have country_name_iso
            if "annotations" in entry:
                assert "country_name_iso" not in entry["annotations"]
