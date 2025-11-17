"""Tests for RDAP bootstrap JSON parsing."""

from pathlib import Path

from src.parse.rdap_json import parse_rdap_json

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source"


def test_parse_rdap_json_total_tlds():
    """Test that parse_rdap_json correctly counts total TLDs."""
    fixture_path = FIXTURES_DIR / "rdap.json"

    results = parse_rdap_json(fixture_path)

    # Total TLDs in the fixture
    assert results["total_tlds"] == 56


def test_parse_rdap_json_unique_servers():
    """Test that parse_rdap_json correctly counts unique RDAP servers."""
    fixture_path = FIXTURES_DIR / "rdap.json"

    results = parse_rdap_json(fixture_path)

    # Unique RDAP servers
    assert results["unique_servers"] == 11


def test_parse_rdap_json_server_list():
    """Test that parse_rdap_json returns the list of unique servers."""
    fixture_path = FIXTURES_DIR / "rdap.json"

    results = parse_rdap_json(fixture_path)

    # Check some specific servers are in the list
    assert "https://pubapi.registry.google/rdap/" in results["servers"]
    assert "https://rdap.iana.org/" in results["servers"]
    assert "https://rdap.centralnic.com/biz/" in results["servers"]

    # Verify it's returning unique servers
    assert len(results["servers"]) == results["unique_servers"]
