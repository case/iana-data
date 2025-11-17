"""Tests for root zone database HTML parsing."""

from pathlib import Path

from src.parse.root_db_html import parse_root_db_html

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source"


def test_parse_root_db_html_total_entries():
    """Test that parse_root_db_html correctly counts total TLD entries."""
    fixture_path = FIXTURES_DIR / "root.html"

    results = parse_root_db_html(fixture_path)

    # Total entries in the fixture
    assert results["total"] == 36


def test_parse_root_db_html_by_type():
    """Test that parse_root_db_html correctly counts delegated TLDs by type."""
    fixture_path = FIXTURES_DIR / "root.html"

    results = parse_root_db_html(fixture_path)

    # Count total generic types (generic + sponsored + infrastructure + generic-restricted)
    assert results["delegated"]["total_generic"] == 21

    # Count delegated by type
    assert results["delegated"]["by_type"]["generic"] == 18
    assert results["delegated"]["by_type"]["country-code"] == 11
    assert results["delegated"]["by_type"]["sponsored"] == 1
    assert results["delegated"]["by_type"]["infrastructure"] == 1
    assert results["delegated"]["by_type"]["generic-restricted"] == 1
    # test type is undelegated in our fixture


def test_parse_root_db_html_idn_counts():
    """Test that parse_root_db_html correctly identifies and counts delegated IDNs."""
    fixture_path = FIXTURES_DIR / "root.html"

    results = parse_root_db_html(fixture_path)

    # Total delegated IDNs (entries with xn--)
    assert results["delegated"]["total_idns"] == 5

    # Delegated IDNs by type
    assert results["delegated"]["idn_by_type"]["country-code"] == 4
    assert results["delegated"]["idn_by_type"]["generic"] == 1
    # test type IDN is undelegated in our fixture


def test_parse_root_db_html_extracts_domains():
    """Test that parse_root_db_html extracts domain names correctly."""
    fixture_path = FIXTURES_DIR / "root.html"

    results = parse_root_db_html(fixture_path)

    # Check some sample domains are in the list
    domains = [entry["domain"] for entry in results["entries"]]

    assert ".aaa" in domains
    assert ".ac" in domains
    assert ".xn--kpry57d" in domains  # Taiwan IDN
    assert ".xn--flw351e" in domains  # Google IDN


def test_parse_root_db_html_extracts_managers():
    """Test that parse_root_db_html extracts TLD managers correctly."""
    fixture_path = FIXTURES_DIR / "root.html"

    results = parse_root_db_html(fixture_path)

    # Find specific entries and check their managers
    entries_by_domain = {entry["domain"]: entry for entry in results["entries"]}

    assert entries_by_domain[".aaa"]["manager"] == "American Automobile Association, Inc."
    assert entries_by_domain[".ac"]["manager"] == "Internet Computer Bureau Limited"
    assert entries_by_domain[".arpa"]["manager"] == "Internet Architecture Board (IAB)"


def test_parse_root_db_html_unique_managers():
    """Test that parse_root_db_html counts unique TLD managers for delegated TLDs."""
    fixture_path = FIXTURES_DIR / "root.html"

    results = parse_root_db_html(fixture_path)

    # Count unique managers (excluding "Not assigned")
    assert results["delegated"]["unique_managers"] == 28

    # Count unique gTLD managers
    assert results["delegated"]["unique_gtld_managers"] == 18

    # Count unique ccTLD managers
    assert results["delegated"]["unique_cctld_managers"] == 10

    # Verify it's counting unique managers, not total TLDs
    assert results["delegated"]["unique_managers"] < results["delegated"]["total"]


def test_parse_root_db_html_delegation_status():
    """Test that parse_root_db_html correctly identifies delegated vs undelegated TLDs."""
    fixture_path = FIXTURES_DIR / "root.html"

    results = parse_root_db_html(fixture_path)

    # Count delegated vs undelegated
    assert results["delegated"]["total"] == 32
    assert results["undelegated"]["total"] == 4

    # Check specific entries
    entries_by_domain = {entry["domain"]: entry for entry in results["entries"]}

    # Delegated TLDs
    assert entries_by_domain[".aaa"]["delegated"] is True
    assert entries_by_domain[".ac"]["delegated"] is True

    # Undelegated TLDs (manager is "Not assigned")
    assert entries_by_domain[".abarth"]["delegated"] is False
    assert entries_by_domain[".active"]["delegated"] is False
    assert entries_by_domain[".zippo"]["delegated"] is False
