"""Tests for IANA TLD JSON schema validation, and the stored pair's conformance."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from src.config import SOURCE_DIR, SOURCE_FILES
from src.parse.iana_tlds_schema import (
    iana_tlds_conformance_problems,
    iana_tlds_schema_problems,
)
from tests.dated_fixtures import latest_fixture

CORE_FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "core"
SCHEMA_ID = "https://data.iana.org/TLD/v1/tlds-schema.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> Any:
    return _load(latest_fixture(CORE_FIXTURES, "iana-tlds-schema.json"))


def _fixture_with(path: list[Any], value: Any) -> Any:
    """The dated TLD JSON fixture with the value at ``path`` replaced."""
    document = copy.deepcopy(_load(latest_fixture(CORE_FIXTURES, "iana-tlds.json")))
    node = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return document


# --- The stored pair ---


def test_stored_iana_tlds_json_conforms_to_the_stored_schema():
    stored_schema = _load(Path(SOURCE_DIR) / SOURCE_FILES["IANA_TLDS_SCHEMA"])
    document = _load(Path(SOURCE_DIR) / SOURCE_FILES["IANA_TLDS"])
    assert document["domains"], "the stored IANA TLD JSON has no records"

    assert iana_tlds_schema_problems(stored_schema) == []
    assert iana_tlds_conformance_problems(document, stored_schema) == []


def test_dated_fixtures_are_a_conforming_pair(schema):
    document = _load(latest_fixture(CORE_FIXTURES, "iana-tlds.json"))

    assert iana_tlds_schema_problems(schema) == []
    assert iana_tlds_conformance_problems(document, schema) == []


# --- Conformance ---


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["domains", 0, "status"], "pending"),
        (["domains", 0, "type"], "sponsored"),
        (["meta", "specversion"], 2),
        (["domains", 0, "nameservers"], None),
        (["domains", 0, "whois_server"], "-not-a-hostname-"),
        (["domains", 0, "registration_url"], "ftp://nic.example"),
        (["domains", 0, "rdap_base_urls"], ["https://rdap.example"]),
        (["domains", 0, "ds_records", 0, "key_tag"], 70000),
        (["domains", 0, "ds_records", 0, "digest"], "XYZ"),
        (["meta", "generated"], "yesterday"),
    ],
)
def test_a_document_that_breaks_the_schema_has_problems(schema, path, value):
    assert iana_tlds_conformance_problems(_fixture_with(path, value), schema)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["meta", "generated"], "2026-99-99T99:99:99Z"),
        (["domains", 0, "registration_url"], "https://example.com:bad/"),
        (["domains", 0, "rdap_base_urls"], ["https://example.com:bad/"]),
        (["domains", 0, "whois_server"], "a" * 64 + ".example"),
        (["domains", 0, "nameservers", 0, "name"], "a" * 64 + ".example"),
        (["domains", 0, "nameservers", 0, "ipv4"], ["999.1.1.1"]),
        (["domains", 0, "nameservers", 0, "ipv6"], ["zz::1"]),
        (["domains", 0, "last_updated"], "2026-02-30"),
    ],
)
def test_a_value_only_its_format_rejects_has_problems(schema, path, value):
    """Each value satisfies the schema's patterns, so only a format check catches it."""
    document = _fixture_with(path, value)

    assert list(Draft202012Validator(schema).iter_errors(document)) == []
    assert iana_tlds_conformance_problems(document, schema)


def test_conformance_problems_stop_at_the_limit(schema):
    document = {"meta": {}, "domains": [{}, {}, {}]}

    assert len(iana_tlds_conformance_problems(document, schema, limit=2)) == 2


# --- Is this IANA's schema at all ---


@pytest.mark.parametrize(
    ("candidate", "fragment"),
    [
        ([], "expected an object"),
        ("schema", "expected an object"),
        ({}, "$id is None"),
        ({"$id": "https://example.com/other.json", "type": "object"}, "$id is"),
        ({"$id": SCHEMA_ID, "type": 7}, "not a valid JSON Schema"),
        ({"$id": SCHEMA_ID}, "accepts a TLD record that has no fields"),
        (
            {"$id": SCHEMA_ID, "type": "object", "required": ["meta", "domains"]},
            "accepts a TLD record that has no fields",
        ),
    ],
    ids=[
        "array",
        "string",
        "accepts-everything",
        "another-schema",
        "malformed-schema",
        "id-only",
        "no-record-definition",
    ],
)
def test_a_payload_that_is_not_ianas_schema_has_problems(candidate, fragment):
    problems = iana_tlds_schema_problems(candidate)

    assert len(problems) == 1
    assert fragment in problems[0]


def _without_record_rules(schema: Any) -> Any:
    """IANA's schema with its meta rules intact and every record rule removed."""
    weakened = copy.deepcopy(schema)
    weakened["properties"]["domains"] = {"type": "array"}
    return weakened


def test_a_schema_that_keeps_meta_rules_but_drops_record_rules_has_problems(schema):
    """Rejecting the probe for its meta must not pass for constraining records."""
    weakened = _without_record_rules(schema)
    arbitrary = {"meta": _fixture_with(["meta", "specversion"], 1)["meta"]}
    arbitrary["domains"] = [{"anything": "at all"}]
    assert iana_tlds_conformance_problems(arbitrary, weakened) == []

    assert iana_tlds_schema_problems(weakened) == [
        "schema accepts a TLD record that has no fields"
    ]


@pytest.mark.parametrize(
    "reference",
    [
        "https://example.invalid/other-schema.json",
        "file:///etc/hosts",
        "other-schema.json#/$defs/domain",
    ],
)
def test_a_schema_that_refers_outside_itself_is_refused_without_a_request(
    schema, reference, monkeypatch
):
    def no_network(*args, **kwargs):
        raise AssertionError("the validator tried to retrieve a reference")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    external = copy.deepcopy(schema)
    external["properties"]["domains"]["items"] = {"$ref": reference}
    document = _load(latest_fixture(CORE_FIXTURES, "iana-tlds.json"))

    (problem,) = iana_tlds_schema_problems(external)
    assert problem.startswith("schema refers outside itself:")
    (problem,) = iana_tlds_conformance_problems(document, external)
    assert problem.startswith("schema refers outside itself:")


def test_references_inside_the_schema_still_resolve(schema):
    assert "$ref" in json.dumps(schema)

    assert iana_tlds_schema_problems(schema) == []
