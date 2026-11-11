"""Tests for the IANA TLD JSON parser."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from src.parse.iana_tlds_json import (
    IanaTldsError,
    iana_tlds_json_content_changed,
    load_iana_tlds,
    parse_iana_tlds,
)
from tests.dated_fixtures import latest_fixture
from tests.iana_tlds_documents import contact as _contact
from tests.iana_tlds_documents import document as _document
from tests.iana_tlds_documents import domain as _domain
from tests.iana_tlds_documents import not_delegated as _not_delegated

CORE_FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "core"


# --- Happy path ---


def test_parse_iana_tlds_maps_every_consumed_field():
    (record,) = parse_iana_tlds(_document())

    assert record.name == "example"
    assert record.status == "active"
    assert record.type == "generic"
    assert record.script_code == "Latn"
    assert record.ulabel is None
    assert record.iso3166_code is None
    assert record.delegation_round == "2012"
    assert (record.manager, record.admin, record.tech) == (
        "Manager Org",
        "Admin Org",
        "Tech Org",
    )
    assert [(ns.name, ns.ipv4, ns.ipv6) for ns in record.nameservers] == [
        ("a.nic.example", ("192.0.2.1",), ("2001:db8::1",))
    ]
    assert [
        (ds.key_tag, ds.algorithm, ds.digest_type, ds.digest)
        for ds in record.ds_records
    ] == [(1, 8, 2, "ab12")]
    assert record.rdap_base_urls == ("https://rdap.example/",)
    assert record.whois_server == "whois.nic.example"
    assert record.registration_url == "https://nic.example"
    assert (record.delegation, record.revocation) == ("2014-01-02", None)
    assert record.last_updated == "2026-01-02"


def test_parse_iana_tlds_reads_idn_cctld_fields():
    domain = _domain(
        name="xn--kpry57d",
        ulabel="台灣",
        type="country-code",
        script_code="Hani",
        iso3166_code="TW",
        annotations={
            "language_code": "zh",
            "transliteration": "taiwan",
            "translation": "Taiwan",
        },
    )

    (record,) = parse_iana_tlds(_document(domain))

    assert record.ulabel == "台灣"
    assert record.iso3166_code == "TW"
    assert record.delegation_round is None
    assert (record.language_code, record.transliteration, record.translation) == (
        "zh",
        "taiwan",
        "Taiwan",
    )


def test_parse_iana_tlds_preserves_document_order():
    names = ["zz", "aa", "mm"]

    records = parse_iana_tlds(_document(*[_domain(name=name) for name in names]))

    assert [record.name for record in records] == names


def test_parse_iana_tlds_ignores_unknown_keys_at_every_level():
    document = _document(_domain(future_field={"x": 1}))
    document["future_top_level"] = True
    document["meta"]["future_meta"] = "x"
    document["domains"][0]["annotations"]["future_annotation"] = "x"
    document["domains"][0]["nameservers"][0]["future_ns"] = "x"

    (record,) = parse_iana_tlds(document)

    assert record.name == "example"


def test_parse_iana_tlds_accepts_hostnames_and_ports_at_their_limits():
    """The guards must not be too broad: a 63-octet label and a real port are valid."""
    host = "a" * 63 + ".example"
    domain = _domain(
        whois_server=host,
        nameservers=[{"name": host, "ipv4": [], "ipv6": []}],
        rdap_base_urls=["https://rdap.example:8443/"],
    )

    (record,) = parse_iana_tlds(_document(domain))

    assert record.whois_server == host
    assert record.nameservers[0].name == host
    assert record.rdap_base_urls == ("https://rdap.example:8443/",)


def test_parse_iana_tlds_normalizes_ipv6_to_compressed_form():
    domain = _domain(
        nameservers=[
            {
                "name": "a.nic.example",
                "ipv4": [],
                "ipv6": ["2001:0DB8:0000:0000:0000:0000:0000:0001"],
            }
        ]
    )

    (record,) = parse_iana_tlds(_document(domain))

    assert record.nameservers[0].ipv6 == ("2001:db8::1",)


# --- Null-able fields ---


def test_parse_iana_tlds_reserved_record_with_every_nullable_field_null():
    domain = _not_delegated(
        "reserved",
        name="local",
        type="special-use",
        annotations={},
        whois_server=None,
        registration_url=None,
        last_updated=None,
        purpose="Used by Multicast DNS",
        remarks="Some *Markdown*.",
    )

    (record,) = parse_iana_tlds(_document(domain))

    assert (record.manager, record.admin, record.tech) == (None, None, None)
    assert record.nameservers == ()
    assert record.ds_records == ()
    assert record.rdap_base_urls == ()
    assert record.whois_server is None
    assert record.registration_url is None
    assert (record.delegation, record.revocation) == (None, None)
    assert record.last_updated is None
    assert record.purpose == "Used by Multicast DNS"
    assert record.remarks == "Some *Markdown*."


def test_parse_iana_tlds_null_organizations_inside_present_objects():
    domain = _domain(
        manager={"organization": None, "address": None, "last_updated": None},
        contacts={"admin": _contact(None), "tech": _contact(None)},
    )

    (record,) = parse_iana_tlds(_document(domain))

    assert (record.manager, record.admin, record.tech) == (None, None, None)


@pytest.mark.parametrize("date", ["1985", "1985-01", "1985-01-01"])
def test_parse_iana_tlds_accepts_event_dates_at_recorded_precision(date):
    domain = _domain(events={"delegation": date, "revocation": None})

    (record,) = parse_iana_tlds(_document(domain))

    assert record.delegation == date


# --- Fail closed ---


def _with(path: list[Any], value: Any) -> dict[str, Any]:
    """A valid document with the value at ``path`` replaced."""
    document = _document()
    node: Any = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return document


def _without(path: list[Any]) -> dict[str, Any]:
    """A valid document with the key at ``path`` removed."""
    document = _document()
    node: Any = document
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return document


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (["domains", 0, "status"], "pending", "status"),
        (["domains", 0, "status"], "Active", "status"),
        (["domains", 0, "type"], "sponsored", "type"),
        (["domains", 0, "type"], "infrastructure", "type"),
        (["meta", "specversion"], 2, "specversion"),
        (["meta", "specversion"], "1", "specversion"),
        (["meta", "specversion"], True, "specversion"),
        (["meta", "specversion"], 1.0, "specversion"),
    ],
)
def test_parse_iana_tlds_rejects_unknown_enum_values(path, value, message):
    with pytest.raises(IanaTldsError, match=message):
        parse_iana_tlds(_with(path, value))


@pytest.mark.parametrize(
    "path",
    [
        ["meta"],
        ["domains"],
        ["meta", "specversion"],
        ["domains", 0, "name"],
        ["domains", 0, "status"],
        ["domains", 0, "type"],
        ["domains", 0, "script_code"],
        ["domains", 0, "annotations"],
        ["domains", 0, "manager"],
        ["domains", 0, "contacts"],
        ["domains", 0, "nameservers"],
        ["domains", 0, "ds_records"],
        ["domains", 0, "rdap_base_urls"],
        ["domains", 0, "whois_server"],
        ["domains", 0, "registration_url"],
        ["domains", 0, "events"],
        ["domains", 0, "last_updated"],
        ["domains", 0, "manager", "organization"],
        ["domains", 0, "contacts", "admin"],
        ["domains", 0, "contacts", "tech", "organization"],
        ["domains", 0, "nameservers", 0, "name"],
        ["domains", 0, "nameservers", 0, "ipv4"],
        ["domains", 0, "nameservers", 0, "ipv6"],
        ["domains", 0, "ds_records", 0, "digest"],
        ["domains", 0, "events", "delegation"],
        ["domains", 0, "events", "revocation"],
    ],
)
def test_parse_iana_tlds_rejects_a_missing_required_key(path):
    with pytest.raises(IanaTldsError, match=str(path[-1])):
        parse_iana_tlds(_without(path))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["meta"], []),
        (["domains"], {}),
        (["domains", 0], "example"),
        (["domains", 0, "name"], 7),
        (["domains", 0, "name"], None),
        (["domains", 0, "ulabel"], 7),
        (["domains", 0, "script_code"], None),
        (["domains", 0, "iso3166_code"], "tw"),
        (["domains", 0, "annotations"], None),
        (["domains", 0, "annotations", "delegation_round"], 2012),
        (["domains", 0, "manager"], "Manager Org"),
        (["domains", 0, "manager", "organization"], 7),
        (["domains", 0, "contacts"], []),
        (["domains", 0, "contacts", "admin"], None),
        (["domains", 0, "nameservers"], None),
        (["domains", 0, "nameservers", 0], "a.nic.example"),
        (["domains", 0, "nameservers", 0, "ipv4"], "192.0.2.1"),
        (["domains", 0, "nameservers", 0, "ipv4"], ["not-an-ip"]),
        (["domains", 0, "nameservers", 0, "ipv4"], ["2001:db8::1"]),
        (["domains", 0, "nameservers", 0, "ipv6"], ["192.0.2.1"]),
        (["domains", 0, "ds_records"], {}),
        (["domains", 0, "ds_records", 0, "key_tag"], "1"),
        (["domains", 0, "ds_records", 0, "algorithm"], True),
        (["domains", 0, "ds_records", 0, "digest"], 12),
        (["domains", 0, "rdap_base_urls"], "https://rdap.example/"),
        (["domains", 0, "rdap_base_urls"], [None]),
        (["domains", 0, "rdap_base_urls"], ["ftp://rdap.example/"]),
        (["domains", 0, "rdap_base_urls"], ["https:///"]),
        (["domains", 0, "rdap_base_urls"], ["https://rdap.example/ x"]),
        (["domains", 0, "rdap_base_urls"], ["https://[::1/"]),
        (["domains", 0, "rdap_base_urls"], ["rdap.example"]),
        (["domains", 0, "rdap_base_urls"], ["https://rdap.example:bad/"]),
        (["domains", 0, "rdap_base_urls"], ["https://rdap.example:99999/"]),
        (["domains", 0, "whois_server"], "a" * 64 + ".example"),
        (["domains", 0, "whois_server"], "Whois.Nic.Example"),
        (["domains", 0, "whois_server"], "localhost"),
        (["domains", 0, "whois_server"], "-whois.example"),
        (["domains", 0, "whois_server"], ".".join(["a" * 60] * 5)),
        (["domains", 0, "nameservers", 0, "name"], "a" * 64 + ".example"),
        (["domains", 0, "nameservers", 0, "name"], "a.nic.example."),
        (["domains", 0, "whois_server"], 43),
        (["domains", 0, "registration_url"], ["https://nic.example"]),
        (["domains", 0, "purpose"], 1),
        (["domains", 0, "remarks"], None),
        (["domains", 0, "events"], None),
        (["domains", 0, "events", "delegation"], 2014),
        (["domains", 0, "events", "revocation"], "last year"),
        (["domains", 0, "events", "delegation"], "2014-13"),
        (["domains", 0, "events", "delegation"], "2014-00"),
        (["domains", 0, "events", "delegation"], "2014-02-30"),
        (["domains", 0, "events", "delegation"], "2014-13-45"),
        (["domains", 0, "events", "delegation"], "0000"),
        (["domains", 0, "last_updated"], 20260102),
        (["domains", 0, "last_updated"], "2026-02-30"),
        (["domains", 0, "last_updated"], "2026"),
    ],
)
def test_parse_iana_tlds_rejects_a_wrong_type(path, value):
    with pytest.raises(IanaTldsError):
        parse_iana_tlds(_with(path, value))


# --- The schema's cross-field rules ---


def _reserved_without_purpose() -> dict[str, Any]:
    domain = _not_delegated("reserved")
    del domain["purpose"]
    return domain


@pytest.mark.parametrize("status", ["retired", "eligible", "reserved"])
def test_parse_iana_tlds_accepts_each_status_that_is_not_active(status):
    (record,) = parse_iana_tlds(_document(_not_delegated(status)))

    assert record.status == status
    assert record.nameservers == ()


@pytest.mark.parametrize(
    ("domain", "message"),
    [
        (_domain(manager=None), "active without a manager and contacts"),
        (_domain(contacts=None), "active without a manager and contacts"),
        (_domain(nameservers=[]), "active without nameservers"),
        (
            _not_delegated("retired", nameservers=_domain()["nameservers"]),
            "retired but has nameservers or DS records",
        ),
        (
            _not_delegated("eligible", ds_records=_domain()["ds_records"]),
            "eligible but has nameservers or DS records",
        ),
        (
            _not_delegated(
                "retired", events={"delegation": "2014", "revocation": None}
            ),
            "retired without a revocation date",
        ),
        (_reserved_without_purpose(), "reserved without a purpose"),
        (_domain(name="xn--kpry57d"), "IDN without a ulabel"),
        (
            _domain(name="xn--kpry57d", ulabel="台灣", type="country-code"),
            "IDN ccTLD without an iso3166_code",
        ),
    ],
)
def test_parse_iana_tlds_rejects_a_broken_cross_field_rule(domain, message):
    with pytest.raises(IanaTldsError, match=message):
        parse_iana_tlds(_document(domain))


def test_parse_iana_tlds_cross_field_rules_spare_valid_neighbours():
    """The guards must not be too broad: these shapes are all legitimate."""
    domains = [
        _domain(name="aa", ds_records=[]),
        _domain(name="xn--flw351e", ulabel="谷歌"),
        _domain(name="tw", type="country-code"),
        _not_delegated("eligible", name="bl", type="country-code"),
        _not_delegated(
            "retired",
            name="um",
            manager={"organization": None, "address": None, "last_updated": None},
        ),
    ]

    assert len(parse_iana_tlds(_document(*domains))) == 5


@pytest.mark.parametrize(
    "name",
    ["", "Example", "../etc", "a/b", "a.b", "-ab", "ab-", "a" * 64, "exa mple"],
)
def test_parse_iana_tlds_rejects_a_name_that_is_not_an_ldh_label(name):
    """The name becomes a file name under data/generated/tld/."""
    with pytest.raises(IanaTldsError, match="name"):
        parse_iana_tlds(_document(_domain(name=name)))


def test_parse_iana_tlds_rejects_empty_domains():
    document = _document()
    document["domains"] = []

    with pytest.raises(IanaTldsError, match="domains"):
        parse_iana_tlds(document)


def test_parse_iana_tlds_rejects_a_duplicate_name():
    document = _document(_domain(), _domain(name="other"), _domain())

    with pytest.raises(IanaTldsError, match="duplicate.*example"):
        parse_iana_tlds(document)


@pytest.mark.parametrize("document", [None, [], "tlds", 7])
def test_parse_iana_tlds_rejects_a_non_object_document(document):
    with pytest.raises(IanaTldsError):
        parse_iana_tlds(document)


def test_parse_iana_tlds_error_names_the_record():
    document = _document(_domain(), _domain(name="broken", status="pending"))

    with pytest.raises(IanaTldsError, match="broken"):
        parse_iana_tlds(document)


# --- Loading from disk ---


def test_load_iana_tlds_reads_the_dated_fixture():
    records = load_iana_tlds(latest_fixture(CORE_FIXTURES, "iana-tlds.json"))
    by_name = {record.name: record for record in records}

    assert {record.status for record in records} == {
        "active",
        "retired",
        "eligible",
        "reserved",
    }
    assert {record.type for record in records} == {
        "generic",
        "country-code",
        "special-use",
        "test",
    }
    assert by_name["xn--kpry57d"].iso3166_code == "TW"
    assert by_name["xn--flw351e"].type == "generic"
    assert by_name["arpa"].type == "special-use"
    assert by_name["local"].manager is None


def test_load_iana_tlds_missing_file_raises(tmp_path):
    with pytest.raises(IanaTldsError, match="missing.json"):
        load_iana_tlds(tmp_path / "missing.json")


def test_load_iana_tlds_invalid_json_raises(tmp_path):
    path = tmp_path / "iana-tlds.json"
    path.write_text('{"meta": ', encoding="utf-8")

    with pytest.raises(IanaTldsError, match="iana-tlds.json"):
        load_iana_tlds(path)


def test_load_iana_tlds_wrong_shape_raises_naming_the_file(tmp_path):
    path = tmp_path / "iana-tlds.json"
    path.write_text(json.dumps(_document(_domain(status="pending"))), encoding="utf-8")

    with pytest.raises(IanaTldsError, match=r"iana-tlds\.json.*status"):
        load_iana_tlds(path)


def test_load_iana_tlds_reads_utf8_regardless_of_locale(tmp_path):
    path = tmp_path / "iana-tlds.json"
    domain = _domain(name="xn--kpry57d", ulabel="台灣")
    path.write_bytes(json.dumps(_document(domain), ensure_ascii=False).encode("utf-8"))

    (record,) = load_iana_tlds(path)

    assert record.ulabel == "台灣"


# --- Content-changed validator ---


def _write(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def test_content_changed_ignores_meta_generated(tmp_path):
    path = tmp_path / "iana-tlds.json"
    _write(path, _document())
    regenerated = _document()
    regenerated["meta"]["generated"] = "2026-11-11T18:19:02+00:00"

    assert iana_tlds_json_content_changed(path, json.dumps(regenerated)) is False


def test_content_changed_ignores_formatting(tmp_path):
    path = tmp_path / "iana-tlds.json"
    _write(path, _document())

    assert (
        iana_tlds_json_content_changed(path, json.dumps(_document(), indent=4)) is False
    )


def test_content_changed_detects_a_changed_record(tmp_path):
    path = tmp_path / "iana-tlds.json"
    _write(path, _document())
    changed = _document(_domain(whois_server="whois.other.example"))

    assert iana_tlds_json_content_changed(path, json.dumps(changed)) is True


def test_content_changed_detects_a_reordered_record_list(tmp_path):
    path = tmp_path / "iana-tlds.json"
    _write(path, _document(_domain(name="aa"), _domain(name="bb")))
    reordered = _document(_domain(name="bb"), _domain(name="aa"))

    assert iana_tlds_json_content_changed(path, json.dumps(reordered)) is True


def test_content_changed_detects_other_meta_changes(tmp_path):
    path = tmp_path / "iana-tlds.json"
    _write(path, _document())
    bumped = copy.deepcopy(_document())
    bumped["meta"]["specversion"] = 2

    assert iana_tlds_json_content_changed(path, json.dumps(bumped)) is True


def test_content_changed_compares_non_object_documents_whole(tmp_path):
    path = tmp_path / "iana-tlds.json"
    path.write_text("[1]", encoding="utf-8")

    assert iana_tlds_json_content_changed(path, "[1]") is False
    assert iana_tlds_json_content_changed(path, "[2]") is True


def test_content_changed_when_no_stored_file(tmp_path):
    assert (
        iana_tlds_json_content_changed(
            tmp_path / "absent.json", json.dumps(_document())
        )
        is True
    )


def test_content_changed_when_stored_file_is_unparseable(tmp_path):
    path = tmp_path / "iana-tlds.json"
    path.write_text("{", encoding="utf-8")

    assert iana_tlds_json_content_changed(path, json.dumps(_document())) is True


def test_content_changed_when_new_content_is_unparseable(tmp_path):
    path = tmp_path / "iana-tlds.json"
    _write(path, _document())

    assert iana_tlds_json_content_changed(path, "{") is True
