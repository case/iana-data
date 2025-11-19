"""Tests for root zone database HTML parsing."""

from pathlib import Path

from src.parse.root_db_html import derive_type_from_iana_tag, parse_root_db_html

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


def test_parse_root_db_html_total_entries():
    """Test that parse_root_db_html returns all TLD entries."""
    fixture_path = FIXTURES_DIR / "root.html"

    entries = parse_root_db_html(fixture_path)

    # Total entries in the fixture
    assert len(entries) == 36


def test_parse_root_db_html_by_type():
    """Test that parse_root_db_html returns entries with correct type data."""
    fixture_path = FIXTURES_DIR / "root.html"

    entries = parse_root_db_html(fixture_path)

    # Filter to delegated entries and count by type
    delegated = [e for e in entries if e.get("delegated", True)]
    by_type = {}
    for entry in delegated:
        entry_type = entry["type"]
        by_type[entry_type] = by_type.get(entry_type, 0) + 1

    # Count total generic types (generic + sponsored + infrastructure + generic-restricted)
    generic_types = ["generic", "sponsored", "infrastructure", "generic-restricted"]
    total_generic = sum(by_type.get(t, 0) for t in generic_types)
    assert total_generic == 21

    # Count delegated by type
    assert by_type["generic"] == 18
    assert by_type["country-code"] == 11
    assert by_type["sponsored"] == 1
    assert by_type["infrastructure"] == 1
    assert by_type["generic-restricted"] == 1
    # test type is undelegated in our fixture


def test_parse_root_db_html_idn_counts():
    """Test that parse_root_db_html returns entries with IDN domains."""
    fixture_path = FIXTURES_DIR / "root.html"

    entries = parse_root_db_html(fixture_path)

    # Filter to delegated IDNs (domains starting with .xn--)
    delegated = [e for e in entries if e.get("delegated", True)]
    delegated_idns = [e for e in delegated if e["domain"].startswith(".xn--")]

    # Total delegated IDNs (entries with xn--)
    assert len(delegated_idns) == 5

    # Delegated IDNs by type
    idn_by_type = {}
    for entry in delegated_idns:
        entry_type = entry["type"]
        idn_by_type[entry_type] = idn_by_type.get(entry_type, 0) + 1

    assert idn_by_type["country-code"] == 4
    assert idn_by_type["generic"] == 1
    # test type IDN is undelegated in our fixture


def test_parse_root_db_html_extracts_domains():
    """Test that parse_root_db_html extracts domain names correctly."""
    fixture_path = FIXTURES_DIR / "root.html"

    entries = parse_root_db_html(fixture_path)

    # Check some sample domains are in the list
    domains = [entry["domain"] for entry in entries]

    assert ".aaa" in domains
    assert ".ac" in domains
    assert ".xn--kpry57d" in domains  # Taiwan IDN
    assert ".xn--flw351e" in domains  # Google IDN


def test_parse_root_db_html_extracts_managers():
    """Test that parse_root_db_html extracts TLD managers correctly."""
    fixture_path = FIXTURES_DIR / "root.html"

    entries = parse_root_db_html(fixture_path)

    # Find specific entries and check their managers
    entries_by_domain = {entry["domain"]: entry for entry in entries}

    assert entries_by_domain[".aaa"]["manager"] == "American Automobile Association, Inc."
    assert entries_by_domain[".ac"]["manager"] == "Internet Computer Bureau Limited"
    assert entries_by_domain[".arpa"]["manager"] == "Internet Architecture Board (IAB)"


def test_parse_root_db_html_unique_managers():
    """Test that parse_root_db_html returns entries with manager data."""
    fixture_path = FIXTURES_DIR / "root.html"

    entries = parse_root_db_html(fixture_path)

    # Filter to delegated entries
    delegated = [e for e in entries if e.get("delegated", True)]

    # Count unique managers (excluding "Not assigned")
    unique_managers = set(e["manager"] for e in delegated)
    assert len(unique_managers) == 28

    # Count unique gTLD managers
    generic_types = ["generic", "sponsored", "infrastructure", "generic-restricted"]
    gtld_managers = set(
        e["manager"] for e in delegated if e["type"] in generic_types
    )
    assert len(gtld_managers) == 18

    # Count unique ccTLD managers
    cctld_managers = set(
        e["manager"] for e in delegated if e["type"] == "country-code"
    )
    assert len(cctld_managers) == 10

    # Verify it's counting unique managers, not total TLDs
    assert len(unique_managers) < len(delegated)


def test_parse_root_db_html_delegation_status():
    """Test that parse_root_db_html correctly identifies delegated vs undelegated TLDs."""
    fixture_path = FIXTURES_DIR / "root.html"

    entries = parse_root_db_html(fixture_path)

    # Count delegated vs undelegated
    delegated = [e for e in entries if e.get("delegated", True)]
    undelegated = [e for e in entries if not e.get("delegated", True)]

    assert len(delegated) == 32
    assert len(undelegated) == 4

    # Check specific entries
    entries_by_domain = {entry["domain"]: entry for entry in entries}

    # Delegated TLDs
    assert entries_by_domain[".aaa"]["delegated"] is True
    assert entries_by_domain[".ac"]["delegated"] is True

    # Undelegated TLDs (manager is "Not assigned")
    assert entries_by_domain[".abarth"]["delegated"] is False
    assert entries_by_domain[".active"]["delegated"] is False
    assert entries_by_domain[".zippo"]["delegated"] is False


def test_derive_type_from_iana_tag_country_code():
    """Test that derive_type_from_iana_tag returns cctld for country-code."""
    result = derive_type_from_iana_tag("country-code")
    assert result == "cctld"


def test_derive_type_from_iana_tag_generic():
    """Test that derive_type_from_iana_tag returns gtld for generic."""
    result = derive_type_from_iana_tag("generic")
    assert result == "gtld"


def test_derive_type_from_iana_tag_sponsored():
    """Test that derive_type_from_iana_tag returns gtld for sponsored."""
    result = derive_type_from_iana_tag("sponsored")
    assert result == "gtld"


def test_derive_type_from_iana_tag_infrastructure():
    """Test that derive_type_from_iana_tag returns gtld for infrastructure."""
    result = derive_type_from_iana_tag("infrastructure")
    assert result == "gtld"


def test_derive_type_from_iana_tag_generic_restricted():
    """Test that derive_type_from_iana_tag returns gtld for generic-restricted."""
    result = derive_type_from_iana_tag("generic-restricted")
    assert result == "gtld"


def test_derive_type_from_iana_tag_test():
    """Test that derive_type_from_iana_tag returns gtld for test."""
    result = derive_type_from_iana_tag("test")
    assert result == "gtld"
