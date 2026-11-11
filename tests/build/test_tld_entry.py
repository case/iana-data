"""Unit tests for building one TLD entry from an IANA TLD JSON record."""

from typing import Any

import pytest

from src.build.tlds import _add_idn_mappings, _build_tld_entry
from src.parse.iana_tlds_json import parse_iana_tlds
from src.parse.organizations import build_resolver
from tests.iana_tlds_documents import document, domain, not_delegated

IDN_CCTLD = {
    "name": "xn--kpry57d",
    "ulabel": "台灣",
    "type": "country-code",
    "script_code": "Hani",
    "iso3166_code": "TW",
    "annotations": {
        "language_code": "zh",
        "transliteration": "taiwan",
        "translation": "Taiwan",
    },
}


def _entry(
    overrides: dict[str, Any] | None = None,
    *,
    archive_entry: dict[str, Any] | None = None,
    rdap_lookup: dict[str, str] | None = None,
    supplemental_rdap: dict[str, dict] | None = None,
    idn_script_mapping: dict[str, str] | None = None,
    manual_annotations: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    (record,) = parse_iana_tlds(document(domain(**(overrides or {}))))
    return _build_tld_entry(
        record,
        archive_entry or {},
        rdap_lookup or {},
        supplemental_rdap or {},
        idn_script_mapping or {},
        {},
        {},
        manual_annotations or {},
        build_resolver([]),
        None,
    )


# --- delegated, iana_tag, type ---


def test_an_active_record_is_delegated():
    entry = _entry()

    assert entry["status"] == "active"
    assert entry["delegated"] is True


@pytest.mark.parametrize("status", ["retired", "eligible", "reserved"])
def test_a_record_that_is_not_active_is_not_delegated(status):
    entry = _entry(not_delegated(status))

    assert entry["status"] == status
    assert entry["delegated"] is False


@pytest.mark.parametrize(
    ("iana_type", "derived"),
    [
        ("generic", "gtld"),
        ("country-code", "cctld"),
        ("special-use", "special-use"),
        ("test", "gtld"),
    ],
)
def test_type_is_derived_from_iana_tag(iana_type, derived):
    entry = _entry({"type": iana_type})

    assert entry["iana_tag"] == iana_type
    assert entry["type"] == derived


# --- Archive seed ---


def test_archive_seed_supplies_tld_created_and_archived_iana_tag():
    archived = {"iana_tag": {"value": "sponsored", "archived_on": "2026-11-10"}}

    entry = _entry(archive_entry={"tld_created": "2001-12-21", "archived": archived})

    assert entry["tld_created"] == "2001-12-21"
    assert entry["archived"] == archived
    assert entry["iana_tag"] == "generic"


def test_no_archive_entry_means_no_tld_created_and_no_archived():
    entry = _entry()

    assert "tld_created" not in entry
    assert "archived" not in entry


# --- Field transformations ---


def test_tld_iso_is_lowercased_so_the_ascii_cctld_gets_its_idn_array():
    idn = _entry(IDN_CCTLD)
    ascii_cctld = _entry({"name": "tw", "type": "country-code"})
    tlds = [ascii_cctld, idn]

    _add_idn_mappings(tlds)

    assert idn["tld_iso"] == "tw"
    assert ascii_cctld["idn"] == ["xn--kpry57d"]


def test_tld_unicode_comes_from_ulabel():
    assert _entry(IDN_CCTLD)["tld_unicode"] == "台灣"
    assert "tld_unicode" not in _entry()


def test_nameserver_name_becomes_hostname_with_asn_objects():
    entry = _entry()

    assert entry["nameservers"] == [
        {
            "hostname": "a.nic.example",
            "ipv4": [
                {"ip": "192.0.2.1", "asn": 0, "as_org": "Unknown", "as_country": "None"}
            ],
            "ipv6": [
                {
                    "ip": "2001:db8::1",
                    "asn": 0,
                    "as_org": "Unknown",
                    "as_country": "None",
                }
            ],
        }
    ]


def test_tld_updated_wraps_last_updated_in_a_list():
    assert _entry()["tld_updated"] == ["2026-01-02"]


def test_tld_updated_is_omitted_when_last_updated_is_null():
    assert "tld_updated" not in _entry({"last_updated": None})


def test_registry_url_and_whois_server_map_directly():
    entry = _entry()

    assert entry["registry_url"] == "https://nic.example"
    assert entry["whois_server"] == "whois.nic.example"


def test_registry_url_and_whois_server_omitted_when_null():
    entry = _entry({"registration_url": None, "whois_server": None})

    assert "registry_url" not in entry
    assert "whois_server" not in entry


def test_orgs_iana_carries_manager_and_contact_organizations():
    assert _entry()["orgs"] == {
        "iana": {"sponsor": "Manager Org", "admin": "Admin Org", "tech": "Tech Org"}
    }


# --- RDAP precedence ---


def test_rdap_server_prefers_the_json_base_url():
    entry = _entry(
        rdap_lookup={"example": "https://bootstrap.example/"},
        supplemental_rdap={"example": {"rdap_server": "https://extra.example/"}},
    )

    assert entry["rdap_server"] == "https://rdap.example/"
    assert entry["annotations"]["rdap_source"] == "IANA"


def test_rdap_server_falls_back_to_the_bootstrap_file():
    entry = _entry(
        {"rdap_base_urls": []},
        rdap_lookup={"example": "https://bootstrap.example/"},
        supplemental_rdap={"example": {"rdap_server": "https://extra.example/"}},
    )

    assert entry["rdap_server"] == "https://bootstrap.example/"
    assert entry["annotations"]["rdap_source"] == "IANA"


def test_rdap_server_falls_back_to_the_supplemental_file_last():
    entry = _entry(
        {"rdap_base_urls": []},
        supplemental_rdap={"example": {"rdap_server": "https://extra.example/"}},
    )

    assert entry["rdap_server"] == "https://extra.example/"
    assert entry["annotations"]["rdap_source"] == "supplemental"


def test_rdap_server_absent_when_no_source_has_one():
    entry = _entry({"rdap_base_urls": []})

    assert "rdap_server" not in entry
    assert "rdap_source" not in entry["annotations"]


def test_repeated_identical_rdap_base_url_is_one_url():
    entry = _entry({"rdap_base_urls": ["https://rdap.example/"] * 2})

    assert entry["rdap_server"] == "https://rdap.example/"


def test_more_than_one_distinct_rdap_base_url_fails_the_build():
    urls = ["https://rdap.example/", "https://rdap2.example/"]

    with pytest.raises(ValueError, match=r"example.*2 distinct RDAP base URLs"):
        _entry({"rdap_base_urls": urls})


# --- language_code precedence ---


def test_language_refined_when_ours_extends_ianas_tag():
    annotations = _entry(
        IDN_CCTLD,
        idn_script_mapping={"xn--kpry57d": "Han-CJK"},
        manual_annotations={"xn--kpry57d": {"language_code": "zh-Hant-TW"}},
    )["annotations"]

    assert annotations["language_code"] == "zh-Hant-TW"
    assert annotations["language_code_source"] == "refined"
    assert annotations["language_name_en"] == "Chinese (Taiwan)"


def test_language_is_ianas_when_ours_does_not_refine_it():
    overrides = {**IDN_CCTLD, "annotations": {"language_code": "ory"}}

    annotations = _entry(overrides, idn_script_mapping={"xn--kpry57d": "Oriya"})[
        "annotations"
    ]

    assert annotations["language_code"] == "ory"
    assert annotations["language_code_source"] == "IANA"
    assert annotations["language_name_en"] == "Odia"


def test_language_is_derived_when_iana_has_none():
    overrides = {**IDN_CCTLD, "annotations": {}}

    annotations = _entry(overrides, idn_script_mapping={"xn--kpry57d": "Han-CJK"})[
        "annotations"
    ]

    assert annotations["language_code"] == "zh"
    assert annotations["language_code_source"] == "derived"
    assert annotations["language_name_en"] == "Chinese"


def test_language_is_ianas_when_we_have_no_script_mapping():
    annotations = _entry(IDN_CCTLD)["annotations"]

    assert annotations["language_code"] == "zh"
    assert annotations["language_code_source"] == "IANA"


def test_no_language_fields_for_an_ascii_tld():
    annotations = _entry()["annotations"]

    assert "language_code" not in annotations
    assert "language_code_source" not in annotations
    assert "language_name_en" not in annotations


def test_iana_language_code_without_an_english_name_fails_the_build():
    overrides = {**IDN_CCTLD, "annotations": {"language_code": "tlh"}}

    with pytest.raises(ValueError, match="No English name for language_code='tlh'"):
        _entry(overrides)


# --- New fields ---


def test_new_iana_fields_are_emitted():
    entry = _entry(IDN_CCTLD, idn_script_mapping={"xn--kpry57d": "Han-CJK"})

    assert entry["tld_script"] == "Han-CJK"
    assert entry["tld_script_code"] == "Hani"
    assert entry["ds_records"] == [
        {"key_tag": 1, "algorithm": 8, "digest_type": 2, "digest": "ab12"}
    ]
    assert entry["events"] == {"delegation": "2014-01-02"}
    assert entry["annotations"]["iana_transliteration"] == "taiwan"
    assert entry["annotations"]["iana_translation_en"] == "Taiwan"


def test_script_code_is_emitted_for_an_ascii_tld():
    entry = _entry()

    assert entry["tld_script_code"] == "Latn"
    assert "tld_script" not in entry


def test_delegation_round_becomes_an_annotation():
    assert _entry()["annotations"]["iana_delegation_round"] == "2012"


def test_events_carry_only_recorded_dates():
    events = {"delegation": "1985", "revocation": "2010-04-01"}

    assert _entry(not_delegated("retired", events=events))["events"] == events
    assert _entry({"events": {"delegation": "2010-04", "revocation": None}})[
        "events"
    ] == {"delegation": "2010-04"}


def test_events_omitted_when_none_is_recorded():
    events = {"delegation": None, "revocation": None}

    assert "events" not in _entry({"events": events})


def test_ds_records_omitted_when_unsigned():
    assert "ds_records" not in _entry({"ds_records": []})


# --- Reserved rows ---


def test_reserved_row_has_no_orgs_nameservers_or_dates():
    reserved = not_delegated(
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

    entry = _entry(reserved)

    assert entry == {
        "tld": "local",
        "tld_script_code": "Latn",
        "status": "reserved",
        "delegated": False,
        "iana_tag": "special-use",
        "type": "special-use",
        "purpose": "Used by Multicast DNS",
        "remarks": "Some *Markdown*.",
    }


def test_nameservers_is_the_last_field_of_a_delegated_entry():
    assert list(_entry())[-1] == "nameservers"
