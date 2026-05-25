"""Tests for ICANN gTLDs JSON Report parsing."""

from pathlib import Path

from src.parse.gtlds_json import parse_gtlds_json

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "icann"
FIXTURE = FIXTURES_DIR / "gtlds.json"


def test_parse_gtlds_json_total_entries():
    """Every record in the curated fixture is parsed."""
    records = parse_gtlds_json(FIXTURE)

    assert len(records) == 7


def test_parse_gtlds_json_tld_keyed_lookup():
    """Records are keyed by bare lowercase TLD (no leading dot)."""
    records = parse_gtlds_json(FIXTURE)

    assert "bestbuy" in records
    assert "museum" in records
    # IDN gTLDs are keyed by their A-label
    assert any(tld.startswith("xn--") for tld in records)


def test_parse_gtlds_json_field_mapping_active_brand():
    """A representative active brand TLD maps every upstream field to schema names."""
    record = parse_gtlds_json(FIXTURE)["bestbuy"]

    assert record == {
        "registry_operator": "BBY Solutions, Inc.",
        "specification_13": True,
        "third_or_lower_level_registration": False,
        "application_id": "1-1908-53104",
        "registry_operator_country_code": None,
        "date_contract_signed": "2015-07-31",
        "date_delegated": "2016-07-19",
        "contract_terminated": False,
        "date_removed": None,
    }


def test_parse_gtlds_json_third_level_registration_preserved():
    """third_or_lower_level_registration True survives (e.g. .museum)."""
    record = parse_gtlds_json(FIXTURE)["museum"]

    assert record["third_or_lower_level_registration"] is True
    assert record["specification_13"] is False


def test_parse_gtlds_json_terminated_preserves_nulls():
    """A terminated TLD keeps its null fields and pairs date_removed with the flag."""
    record = parse_gtlds_json(FIXTURE)["abarth"]

    assert record["contract_terminated"] is True
    assert record["date_removed"] == "2023-06-05"
    assert record["registry_operator"] is None
    assert record["specification_13"] is None
    assert record["application_id"] is None


def test_parse_gtlds_json_excludes_dropped_fields():
    """Dropped and oracle-only upstream fields never appear in output."""
    record = parse_gtlds_json(FIXTURE)["bestbuy"]

    # registryClassDomainNameList is null in every record and undocumented.
    assert "registry_class_domain_name_list" not in record
    assert "registryClassDomainNameList" not in record
    # uLabel is only a verification oracle, not stored.
    assert "u_label" not in record
    assert "uLabel" not in record
    # No raw camelCase keys leak through.
    assert "gTLD" not in record
    assert "registryOperator" not in record


def test_parse_gtlds_json_legacy_delegation_backfill_preserved():
    """The 1985-01-01 pre-ICANN delegation backfill survives parsing verbatim."""
    record = parse_gtlds_json(FIXTURE)["com"]

    assert record["date_delegated"] == "1985-01-01"


def test_parse_gtlds_json_contract_terminated_always_bool():
    """contract_terminated is a bool for every record."""
    records = parse_gtlds_json(FIXTURE)

    assert all(isinstance(r["contract_terminated"], bool) for r in records.values())


def test_parse_gtlds_json_missing_file():
    """A missing source file yields an empty map, not an error."""
    assert parse_gtlds_json(Path("/nonexistent/gtlds.json")) == {}
