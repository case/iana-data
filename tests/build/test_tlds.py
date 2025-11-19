"""Integration tests for TLD build process."""

import json
from pathlib import Path

from src.build.tlds import build_tlds_json
from src.config import TLDS_OUTPUT_FILE
from src.parse.rdap_json import parse_rdap_json
from src.parse.root_db_html import parse_root_db_html
from src.parse.tlds_txt import parse_tlds_txt

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


def test_build_tlds_json_creates_file():
    """Test that build_tlds_json creates the output file."""
    result = build_tlds_json()

    # Should return result dict
    assert "total_tlds" in result
    assert "output_file" in result

    # Should create output file
    output_path = Path(TLDS_OUTPUT_FILE)
    assert output_path.exists()


def test_build_tlds_json_has_correct_structure():
    """Test that generated tlds.json has correct top-level structure."""
    build_tlds_json()

    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
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


def test_build_tlds_json_tld_count_matches_source():
    """Test that number of TLDs in output matches root zone source."""
    # Parse root zone to get expected count
    root_zone_entries = parse_root_db_html()
    expected_count = len(root_zone_entries)

    # Build and check output
    result = build_tlds_json()

    assert result["total_tlds"] == expected_count

    # Also verify in the file itself
    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
        data = json.load(f)

    assert len(data["tlds"]) == expected_count


def test_build_tlds_json_has_required_fields():
    """Test that each TLD entry has required fields."""
    build_tlds_json()

    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
        data = json.load(f)

    # Check first few entries have required fields
    for tld_entry in data["tlds"][:10]:
        assert "tld" in tld_entry
        assert "delegated" in tld_entry
        assert "iana_tag" in tld_entry
        assert "type" in tld_entry
        # tld_manager is now in orgs object, which is optional for undelegated TLDs


def test_build_tlds_json_strips_leading_dots():
    """Test that TLDs in output don't have leading dots."""
    build_tlds_json()

    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
        data = json.load(f)

    # Check that no TLD starts with a dot
    for tld_entry in data["tlds"]:
        assert not tld_entry["tld"].startswith(".")


def test_build_tlds_json_derives_type_correctly():
    """Test that type field is correctly derived from iana_tag."""
    build_tlds_json()

    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
        data = json.load(f)

    for tld_entry in data["tlds"]:
        iana_tag = tld_entry["iana_tag"]
        derived_type = tld_entry["type"]

        # Check derivation logic
        if iana_tag == "country-code":
            assert derived_type == "cctld"
        else:
            assert derived_type == "gtld"


def test_build_tlds_json_delegated_status():
    """Test that delegated status is correctly set."""
    build_tlds_json()

    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
        data = json.load(f)

    for tld_entry in data["tlds"]:
        delegated = tld_entry["delegated"]

        # Check logic: delegated TLDs should have orgs with tld_manager
        if delegated:
            assert "orgs" in tld_entry
            assert "tld_manager" in tld_entry["orgs"]
        # Undelegated TLDs may or may not have orgs


def test_build_tlds_json_rdap_servers_present():
    """Test that RDAP servers are included for TLDs that have them."""
    # Get RDAP lookup to know which TLDs should have servers
    rdap_lookup = parse_rdap_json()

    build_tlds_json()

    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
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


def test_build_tlds_json_idn_unicode_field():
    """Test that IDN TLDs have tld_unicode field."""
    build_tlds_json()

    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
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


def test_build_tlds_json_publication_timestamp_format():
    """Test that publication timestamp uses correct format (seconds + Z)."""
    build_tlds_json()

    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
        data = json.load(f)

    publication = data["publication"]

    # Should end with Z
    assert publication.endswith("Z")

    # Should not have microseconds (no decimal point)
    assert "." not in publication

    # Should match format YYYY-MM-DDTHH:MM:SSZ
    # Length should be 20 characters
    assert len(publication) == 20


def test_build_tlds_json_delegated_count_matches_tlds_txt():
    """Test that delegated TLD count matches all-tlds text file."""
    # Parse TLDs text file to get expected count
    tlds_txt_list = parse_tlds_txt()
    expected_delegated_count = len(tlds_txt_list)

    # Build and check output
    build_tlds_json()

    output_path = Path(TLDS_OUTPUT_FILE)
    with open(output_path) as f:
        data = json.load(f)

    # Count delegated TLDs in output
    delegated_tlds = [entry for entry in data["tlds"] if entry["delegated"]]
    actual_delegated_count = len(delegated_tlds)

    # Should match
    assert actual_delegated_count == expected_delegated_count
