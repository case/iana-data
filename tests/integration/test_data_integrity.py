"""Integration tests for data integrity across sources."""

import json
from pathlib import Path

import pytest

from src.config import MANUAL_DIR, SOURCE_DIR, SOURCE_FILES, TLDS_OUTPUT_FILE
from src.parse.rdap_json import parse_rdap_json
from src.parse.root_db_html import parse_root_db_html
from src.parse.supplemental_cctld_rdap import parse_supplemental_cctld_rdap
from src.parse.tlds_txt import parse_tlds_txt

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_supplemental_rdap_does_not_overlap_with_iana_rdap():
    """Test that supplemental ccTLD RDAP data doesn't overlap with IANA RDAP data.

    The supplemental data should only contain TLDs that are NOT already
    in the canonical IANA RDAP bootstrap file.
    """
    # Parse IANA RDAP to get TLDs with canonical RDAP servers
    iana_rdap_path = Path(SOURCE_DIR) / SOURCE_FILES["RDAP_BOOTSTRAP"]
    iana_rdap_lookup = parse_rdap_json(iana_rdap_path)
    iana_tlds = set(iana_rdap_lookup.keys())

    # Parse supplemental ccTLD RDAP data
    supplemental_path = Path(MANUAL_DIR) / "supplemental-cctld-rdap.json"
    supplemental_lookup = parse_supplemental_cctld_rdap(supplemental_path)
    supplemental_tlds = set(supplemental_lookup.keys())

    # Find any overlap
    overlap = iana_tlds & supplemental_tlds

    # Should have no overlap
    assert len(overlap) == 0, (
        f"Found {len(overlap)} TLD(s) in both IANA RDAP and supplemental data: "
        f"{sorted(overlap)}. Supplemental data should only contain TLDs "
        f"not present in the canonical IANA RDAP bootstrap file."
    )


def test_supplemental_rdap_file_exists():
    """Test that supplemental ccTLD RDAP file exists."""
    supplemental_path = Path(MANUAL_DIR) / "supplemental-cctld-rdap.json"
    assert supplemental_path.exists(), (
        f"Supplemental ccTLD RDAP file not found at {supplemental_path}. "
        f"This file should exist in the repository."
    )


def test_supplemental_rdap_has_entries():
    """Test that supplemental ccTLD RDAP file has some entries."""
    supplemental_path = Path(MANUAL_DIR) / "supplemental-cctld-rdap.json"
    supplemental_lookup = parse_supplemental_cctld_rdap(supplemental_path)

    assert len(supplemental_lookup) > 0, (
        "Supplemental ccTLD RDAP file should contain at least one entry"
    )


def test_overlap_detection_works_with_fixtures():
    """Test that overlap detection works correctly using fixture data.

    This test uses fixtures where we intentionally created an overlap
    to verify the test logic actually catches it.
    """
    # Parse IANA RDAP fixture
    iana_rdap_path = FIXTURES_DIR / "source" / "core" / "rdap.json"
    iana_rdap_lookup = parse_rdap_json(iana_rdap_path)
    iana_tlds = set(iana_rdap_lookup.keys())

    # Parse supplemental fixture WITH intentional overlap
    supplemental_path = FIXTURES_DIR / "generated" / "supplemental-cctld-rdap-with-overlap.json"
    supplemental_lookup = parse_supplemental_cctld_rdap(supplemental_path)
    supplemental_tlds = set(supplemental_lookup.keys())

    # Find overlap
    overlap = iana_tlds & supplemental_tlds

    # Should detect the "aaa" overlap we created
    assert len(overlap) > 0, "Test fixture should have intentional overlap"
    assert "aaa" in overlap, "Test fixture should have 'aaa' as overlapping TLD"


def test_no_overlap_in_fixture_data():
    """Test that the normal fixture data has no overlap.

    This verifies that our test fixtures are set up correctly.
    """
    # Parse IANA RDAP fixture
    iana_rdap_path = FIXTURES_DIR / "source" / "core" / "rdap.json"
    iana_rdap_lookup = parse_rdap_json(iana_rdap_path)
    iana_tlds = set(iana_rdap_lookup.keys())

    # Parse supplemental fixture WITHOUT overlap
    supplemental_path = FIXTURES_DIR / "generated" / "supplemental-cctld-rdap.json"
    supplemental_lookup = parse_supplemental_cctld_rdap(supplemental_path)
    supplemental_tlds = set(supplemental_lookup.keys())

    # Find any overlap
    overlap = iana_tlds & supplemental_tlds

    # Should have no overlap in the normal fixtures
    assert len(overlap) == 0, (
        f"Fixture data should have no overlap, but found: {sorted(overlap)}"
    )


def test_delegated_tlds_count_matches_source():
    """Test that delegated TLDs in tlds.json matches count in iana-tlds.txt.

    The IANA TLDs text file contains all delegated TLDs. Our built tlds.json
    should have the same count of delegated TLDs.
    """
    # Parse IANA TLDs text file
    tlds_txt_path = Path(SOURCE_DIR) / SOURCE_FILES["TLD_LIST"]
    tlds_txt_list = parse_tlds_txt(tlds_txt_path)
    expected_delegated_count = len(tlds_txt_list)

    # Parse built tlds.json
    tlds_json_path = Path(TLDS_OUTPUT_FILE)
    assert tlds_json_path.exists(), (
        f"Built tlds.json file not found at {tlds_json_path}. "
        f"Run 'make build' first to generate this file."
    )

    with open(tlds_json_path) as f:
        tlds_data = json.load(f)

    # Count delegated TLDs in output
    delegated_tlds = [entry for entry in tlds_data["tlds"] if entry["delegated"]]
    actual_delegated_count = len(delegated_tlds)

    # Counts should match
    assert actual_delegated_count == expected_delegated_count, (
        f"Delegated TLD count mismatch: "
        f"tlds.json has {actual_delegated_count} delegated TLDs, "
        f"but iana-tlds.txt has {expected_delegated_count} TLDs. "
        f"These should match as iana-tlds.txt contains all delegated TLDs."
    )


def test_undelegated_tlds_count_matches_not_assigned():
    """Test that undelegated TLDs in tlds.json matches 'Not assigned' count in root DB.

    The root DB HTML contains TLDs with manager 'Not assigned' which should
    match the count of undelegated TLDs in our built tlds.json.
    """
    # Parse root DB HTML to count "Not assigned" entries
    root_db_path = Path(SOURCE_DIR) / SOURCE_FILES["ROOT_ZONE_DB"]
    root_db_entries = parse_root_db_html(root_db_path)
    not_assigned_count = sum(
        1 for entry in root_db_entries if entry["manager"] == "Not assigned"
    )

    # Parse built tlds.json
    tlds_json_path = Path(TLDS_OUTPUT_FILE)
    assert tlds_json_path.exists(), (
        f"Built tlds.json file not found at {tlds_json_path}. "
        f"Run 'make build' first to generate this file."
    )

    with open(tlds_json_path) as f:
        tlds_data = json.load(f)

    # Count undelegated TLDs in output
    undelegated_tlds = [entry for entry in tlds_data["tlds"] if not entry["delegated"]]
    undelegated_count = len(undelegated_tlds)

    # Counts should match
    assert undelegated_count == not_assigned_count, (
        f"Undelegated TLD count mismatch: "
        f"tlds.json has {undelegated_count} undelegated TLDs, "
        f"but root DB has {not_assigned_count} 'Not assigned' managers. "
        f"These should match as 'Not assigned' indicates undelegated TLDs."
    )


def test_total_tlds_math_is_correct():
    """Test that delegated + undelegated = total TLDs across all sources.

    This verifies our accounting is correct:
    - Count from iana-tlds.txt (delegated)
    - + Count of undelegated in tlds.json
    - = Total count in root DB HTML
    """
    # Parse IANA TLDs text file (delegated count)
    tlds_txt_path = Path(SOURCE_DIR) / SOURCE_FILES["TLD_LIST"]
    tlds_txt_list = parse_tlds_txt(tlds_txt_path)
    delegated_count = len(tlds_txt_list)

    # Parse built tlds.json (undelegated count)
    tlds_json_path = Path(TLDS_OUTPUT_FILE)
    assert tlds_json_path.exists(), (
        f"Built tlds.json file not found at {tlds_json_path}. "
        f"Run 'make build' first to generate this file."
    )

    with open(tlds_json_path) as f:
        tlds_data = json.load(f)

    undelegated_tlds = [entry for entry in tlds_data["tlds"] if not entry["delegated"]]
    undelegated_count = len(undelegated_tlds)

    # Parse root DB HTML (total count)
    root_db_path = Path(SOURCE_DIR) / SOURCE_FILES["ROOT_ZONE_DB"]
    root_db_entries = parse_root_db_html(root_db_path)
    total_count = len(root_db_entries)

    # Math should add up
    calculated_total = delegated_count + undelegated_count

    assert calculated_total == total_count, (
        f"TLD count math error: "
        f"{delegated_count} delegated (from iana-tlds.txt) + "
        f"{undelegated_count} undelegated (from tlds.json) = "
        f"{calculated_total}, but root DB has {total_count} total TLDs. "
        f"These should match. Difference: {total_count - calculated_total}"
    )


# --- ASN Data Integrity Tests ---


@pytest.fixture
def tlds_json_fixture():
    """Load the tlds.json fixture file."""
    fixture_path = FIXTURES_DIR / "generated" / "tlds.json"
    with open(fixture_path) as f:
        return json.load(f)


def test_fixture_nameserver_ips_have_asn_structure(tlds_json_fixture):
    """Test that nameserver IPs in fixture have the correct ASN metadata structure.

    Each IP should be an object with ip, asn, as_org, and as_country fields.
    """
    # Find a TLD with nameservers that have IPs
    tld_with_ns = None
    for tld in tlds_json_fixture["tlds"]:
        if "nameservers" not in tld:
            continue
        for ns in tld["nameservers"]:
            if isinstance(ns, dict) and (ns.get("ipv4") or ns.get("ipv6")):
                tld_with_ns = tld
                break
        if tld_with_ns:
            break

    assert tld_with_ns is not None, "Fixture should have at least one TLD with nameserver IPs"

    ns = tld_with_ns["nameservers"][0]
    ip_list = ns.get("ipv4") or ns.get("ipv6")
    first_ip = ip_list[0]

    # Should be an object with ASN fields
    assert isinstance(first_ip, dict), (
        f"IP should be an object with ASN metadata, got {type(first_ip)}"
    )
    assert "ip" in first_ip, "IP object should have 'ip' field"
    assert "asn" in first_ip, "IP object should have 'asn' field"
    assert "as_org" in first_ip, "IP object should have 'as_org' field"
    assert "as_country" in first_ip, "IP object should have 'as_country' field"


def test_fixture_nameserver_asn_values_are_valid(tlds_json_fixture):
    """Test that ASN values in fixture are valid integers >= 0."""
    invalid_asns = []

    for tld in tlds_json_fixture["tlds"]:
        if "nameservers" not in tld:
            continue

        for ns in tld["nameservers"]:
            if not isinstance(ns, dict):
                continue
            for ip_obj in ns.get("ipv4", []) + ns.get("ipv6", []):
                if isinstance(ip_obj, dict):
                    asn = ip_obj.get("asn")
                    if not isinstance(asn, int) or asn < 0:
                        invalid_asns.append({
                            "tld": tld["tld"],
                            "ip": ip_obj.get("ip"),
                            "asn": asn,
                        })

    assert len(invalid_asns) == 0, (
        f"Found {len(invalid_asns)} IPs with invalid ASN values: {invalid_asns[:5]}"
    )


def test_fixture_known_asn_values(tlds_json_fixture):
    """Test that fixture has expected ASN values for known IPs.

    The fixture includes Cloudflare (13335) and Google (15169) ASNs.
    """
    # Find the "aaa" TLD which has our test ASN data
    aaa_tld = next(
        (tld for tld in tlds_json_fixture["tlds"] if tld["tld"] == "aaa"),
        None
    )
    assert aaa_tld is not None, "Fixture should have 'aaa' TLD"
    assert "nameservers" in aaa_tld, "'aaa' TLD should have nameservers"

    # Collect all ASNs from the nameservers
    found_asns = set()
    for ns in aaa_tld["nameservers"]:
        if not isinstance(ns, dict):
            continue
        for ip_obj in ns.get("ipv4", []) + ns.get("ipv6", []):
            if isinstance(ip_obj, dict) and "asn" in ip_obj:
                found_asns.add(ip_obj["asn"])

    # Should have Cloudflare and Google ASNs
    assert 13335 in found_asns, "Fixture should include Cloudflare ASN (13335)"
    assert 15169 in found_asns, "Fixture should include Google ASN (15169)"


def test_production_nameserver_structure_if_built():
    """Test that production tlds.json has correct nameserver structure if it exists.

    This test validates the actual built file structure without checking
    specific ASN values (which change with iptoasn data updates).
    """
    tlds_json_path = Path(TLDS_OUTPUT_FILE)
    if not tlds_json_path.exists():
        pytest.skip("Built tlds.json not found. Run 'make build' first.")

    with open(tlds_json_path) as f:
        tlds_data = json.load(f)

    # Find a TLD with nameservers
    tld_with_ns = None
    for tld in tlds_data["tlds"]:
        if "nameservers" in tld and len(tld["nameservers"]) > 0:
            ns = tld["nameservers"][0]
            if isinstance(ns, dict) and (ns.get("ipv4") or ns.get("ipv6")):
                tld_with_ns = tld
                break

    if tld_with_ns is None:
        pytest.skip("No TLDs with nameserver IPs found in production tlds.json")

    ns = tld_with_ns["nameservers"][0]

    # Check nameserver structure
    assert "hostname" in ns, "Nameserver should have 'hostname' field"
    assert "ipv4" in ns, "Nameserver should have 'ipv4' field"
    assert "ipv6" in ns, "Nameserver should have 'ipv6' field"

    # Check IP structure (if there are IPs)
    ip_list = ns.get("ipv4") or ns.get("ipv6")
    if ip_list:
        first_ip = ip_list[0]
        assert isinstance(first_ip, dict), "IP should be an object"
        assert "ip" in first_ip, "IP object should have 'ip' field"
        assert "asn" in first_ip, "IP object should have 'asn' field"
        assert "as_org" in first_ip, "IP object should have 'as_org' field"
        assert "as_country" in first_ip, "IP object should have 'as_country' field"
