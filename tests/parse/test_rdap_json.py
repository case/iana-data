"""Tests for RDAP bootstrap JSON parsing."""

from pathlib import Path

from src.parse.rdap_json import parse_rdap_json

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source"


def test_parse_rdap_json_total_tlds():
    """Test that parse_rdap_json returns TLD lookup map."""
    fixture_path = FIXTURES_DIR / "rdap.json"

    rdap_lookup = parse_rdap_json(fixture_path)

    # Count total TLDs in the fixture
    assert len(rdap_lookup) == 56


def test_parse_rdap_json_unique_servers():
    """Test that parse_rdap_json returns lookup with correct unique servers."""
    fixture_path = FIXTURES_DIR / "rdap.json"

    rdap_lookup = parse_rdap_json(fixture_path)

    # Count unique RDAP servers
    unique_servers = set(rdap_lookup.values())

    assert len(unique_servers) == 11


def test_parse_rdap_json_server_list():
    """Test that parse_rdap_json returns lookup with specific servers."""
    fixture_path = FIXTURES_DIR / "rdap.json"

    rdap_lookup = parse_rdap_json(fixture_path)

    # Collect all servers
    all_servers = set(rdap_lookup.values())

    # Check some specific servers are in the list
    assert "https://pubapi.registry.google/rdap/" in all_servers
    assert "https://rdap.iana.org/" in all_servers
    assert "https://rdap.centralnic.com/biz/" in all_servers

    # Verify count
    assert len(all_servers) == 11
