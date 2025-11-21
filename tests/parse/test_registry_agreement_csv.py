"""Tests for ICANN Registry Agreement CSV parsing."""

from pathlib import Path

from src.parse.registry_agreement_csv import (
    get_normalized_agreement_types,
    parse_agreement_types,
    parse_registry_agreement_csv,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "icann"


def test_parse_registry_agreement_csv_total_entries():
    """Test that parse_registry_agreement_csv returns expected number of entries."""
    fixture_path = FIXTURES_DIR / "registry-agreement-table.csv"

    agreements = parse_registry_agreement_csv(fixture_path)

    assert len(agreements) == 8


def test_parse_registry_agreement_csv_tld_lookup():
    """Test that parse_registry_agreement_csv returns TLD-keyed lookup map."""
    fixture_path = FIXTURES_DIR / "registry-agreement-table.csv"

    agreements = parse_registry_agreement_csv(fixture_path)

    # Check specific TLDs exist in lookup
    assert "aaa" in agreements
    assert "archi" in agreements
    assert "xn--11b4c3d" in agreements


def test_parse_registry_agreement_csv_brand_tld():
    """Test parsing of Brand (Spec 13) TLD."""
    fixture_path = FIXTURES_DIR / "registry-agreement-table.csv"

    agreements = parse_registry_agreement_csv(fixture_path)
    entry = agreements["aaa"]

    assert entry["tld"] == "aaa"
    assert entry["status"] == "active"
    assert entry["operator"] == "American Automobile Association, Inc."
    assert "Brand (Spec 13)" in entry["agreement_types"]
    assert "Base" in entry["agreement_types"]
    assert "Non-Sponsored" in entry["agreement_types"]


def test_parse_registry_agreement_csv_community_tld():
    """Test parsing of Community (Spec 12) TLD without Brand."""
    fixture_path = FIXTURES_DIR / "registry-agreement-table.csv"

    agreements = parse_registry_agreement_csv(fixture_path)
    entry = agreements["archi"]

    assert entry["tld"] == "archi"
    assert entry["status"] == "active"
    assert "Community (Spec 12)" in entry["agreement_types"]
    assert "Brand (Spec 13)" not in entry["agreement_types"]


def test_parse_registry_agreement_csv_terminated_tld():
    """Test parsing of terminated TLD."""
    fixture_path = FIXTURES_DIR / "registry-agreement-table.csv"

    agreements = parse_registry_agreement_csv(fixture_path)
    entry = agreements["abarth"]

    assert entry["tld"] == "abarth"
    assert entry["status"] == "terminated"
    assert entry["operator"] == "Fiat Chrysler Automobiles N.V."


def test_parse_registry_agreement_csv_sponsored_tld():
    """Test parsing of Sponsored TLD (legacy type)."""
    fixture_path = FIXTURES_DIR / "registry-agreement-table.csv"

    agreements = parse_registry_agreement_csv(fixture_path)
    entry = agreements["aero"]

    assert entry["tld"] == "aero"
    assert entry["status"] == "active"
    assert "Sponsored" in entry["agreement_types"]


def test_parse_registry_agreement_csv_idn_tld():
    """Test parsing of IDN TLD with U-Label and Translation."""
    fixture_path = FIXTURES_DIR / "registry-agreement-table.csv"

    agreements = parse_registry_agreement_csv(fixture_path)
    entry = agreements["xn--11b4c3d"]

    assert entry["tld"] == "xn--11b4c3d"
    assert entry["u_label"] == "कॉम"
    assert entry["translation"] == "com"
    assert entry["status"] == "active"


def test_parse_registry_agreement_csv_base_only():
    """Test parsing of TLD with only Base, Non-Sponsored (no special types)."""
    fixture_path = FIXTURES_DIR / "registry-agreement-table.csv"

    agreements = parse_registry_agreement_csv(fixture_path)
    entry = agreements["able"]

    assert entry["tld"] == "able"
    assert "Base" in entry["agreement_types"]
    assert "Non-Sponsored" in entry["agreement_types"]
    assert "Brand (Spec 13)" not in entry["agreement_types"]
    assert "Community (Spec 12)" not in entry["agreement_types"]


def test_parse_registry_agreement_csv_missing_file():
    """Test that missing file returns empty dict."""
    result = parse_registry_agreement_csv(Path("/nonexistent/path.csv"))

    assert result == {}


# Tests for parse_agreement_types utility function


def test_parse_agreement_types_multiple():
    """Test parsing comma-separated agreement types."""
    result = parse_agreement_types("Base, Brand (Spec 13), Non-Sponsored")

    assert result == ["Base", "Brand (Spec 13)", "Non-Sponsored"]


def test_parse_agreement_types_single():
    """Test parsing single agreement type."""
    result = parse_agreement_types("Sponsored")

    assert result == ["Sponsored"]


def test_parse_agreement_types_empty():
    """Test parsing empty string."""
    result = parse_agreement_types("")

    assert result == []


def test_parse_agreement_types_whitespace_handling():
    """Test that whitespace is properly stripped."""
    result = parse_agreement_types("  Base  ,  Non-Sponsored  ")

    assert result == ["Base", "Non-Sponsored"]


# Tests for get_normalized_agreement_types utility function


def test_get_normalized_agreement_types_brand():
    """Test normalization of Brand (Spec 13) to 'brand'."""
    types = ["Base", "Brand (Spec 13)", "Non-Sponsored"]

    result = get_normalized_agreement_types(types)

    assert result == ["base", "brand", "non_sponsored"]


def test_get_normalized_agreement_types_community():
    """Test normalization of Community (Spec 12) to 'community'."""
    types = ["Base", "Community (Spec 12)", "Non-Sponsored"]

    result = get_normalized_agreement_types(types)

    assert result == ["base", "community", "non_sponsored"]


def test_get_normalized_agreement_types_brand_and_community():
    """Test that both Brand and Community are included when both present."""
    types = ["Base", "Brand (Spec 13)", "Community (Spec 12)", "Non-Sponsored"]

    result = get_normalized_agreement_types(types)

    # All types should be normalized and returned in order
    assert result == ["base", "brand", "community", "non_sponsored"]


def test_get_normalized_agreement_types_base_only():
    """Test normalization of Base, Non-Sponsored (no special types)."""
    types = ["Base", "Non-Sponsored"]

    result = get_normalized_agreement_types(types)

    assert result == ["base", "non_sponsored"]


def test_get_normalized_agreement_types_sponsored():
    """Test that Sponsored is normalized correctly."""
    types = ["Sponsored"]

    result = get_normalized_agreement_types(types)

    assert result == ["sponsored"]


def test_get_normalized_agreement_types_empty_list():
    """Test that empty list returns empty list."""
    result = get_normalized_agreement_types([])

    assert result == []


def test_get_normalized_agreement_types_unknown_type():
    """Test that unknown types are not included in output."""
    types = ["Base", "Unknown Type", "Non-Sponsored"]

    result = get_normalized_agreement_types(types)

    assert result == ["base", "non_sponsored"]
