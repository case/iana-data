"""Invariants between the IANA TLD JSON, our curated files, and the built graph.

Each one guards an assumption the build bakes in. If IANA or a curator changes
the data in a way that trips one, the build needs a deliberate review.
"""

import pytest

from src.build.idn_language import LANGUAGE_NAMES_EN
from src.parse.iana_tlds_json import load_iana_tlds
from src.parse.supplemental_cctld_rdap import parse_supplemental_cctld_rdap
from src.parse.tld_archive import ARCHIVED_IANA_TAGS, parse_tld_archive

# Our tld_script name -> IANA's ISO 15924 script_code for the same script.
SCRIPT_NAME_TO_CODE = {
    "Arabic": "Arab",
    "Armenian": "Armn",
    "Bengali": "Beng",
    "Cyrillic": "Cyrl",
    "Devanagari": "Deva",
    "Georgian": "Geor",
    "Greek": "Grek",
    "Gujarati": "Gujr",
    "Gurmukhi": "Guru",
    "Han-CJK": "Hani",
    "Hangul": "Hang",
    "Hebrew": "Hebr",
    "Hiragana": "Hira",
    "Kannada": "Knda",
    "Katakana": "Kana",
    "Lao": "Laoo",
    "Latin": "Latn",
    "Malayalam": "Mlym",
    "Oriya": "Orya",
    "Sinhala": "Sinh",
    "Tamil": "Taml",
    "Telugu": "Telu",
    "Thai": "Thai",
}


@pytest.fixture(scope="module")
def iana_records():
    records = load_iana_tlds()
    assert records, "the IANA TLD JSON has no records"
    return {record.name: record for record in records}


# --- Script: our detected name against IANA's code ---


def test_tld_script_agrees_with_iana_script_code(typed_graph):
    """tld_script comes from our own pipeline; IANA's code must name the same script."""
    with_script = {
        tld: entry for tld, entry in typed_graph.tlds.items() if "tld_script" in entry
    }
    assert with_script, "no built TLD carries tld_script"

    unmapped = sorted(
        {e["tld_script"] for e in with_script.values()} - set(SCRIPT_NAME_TO_CODE)
    )
    assert not unmapped, f"add to SCRIPT_NAME_TO_CODE: {unmapped}"

    disagreements = [
        (tld, entry["tld_script"], entry["tld_script_code"])
        for tld, entry in with_script.items()
        if SCRIPT_NAME_TO_CODE[entry["tld_script"]] != entry["tld_script_code"]
    ]
    assert not disagreements, f"tld_script disagrees with IANA: {disagreements}"


def test_every_idn_has_a_tld_script(typed_graph):
    """An IDN missing from idn-script-mapping.json would skip the agreement check."""
    missing = sorted(
        tld
        for tld, entry in typed_graph.tlds.items()
        if tld.startswith("xn--") and "tld_script" not in entry
    )

    assert not missing, f"IDN TLDs with no tld_script: {missing}"


# --- Language ---


def test_every_iana_language_code_has_an_english_name(iana_records):
    """An unnamed code fails the build; this names the gap before a build does."""
    codes = {r.language_code for r in iana_records.values() if r.language_code}
    assert codes, "the IANA TLD JSON carries no language_code"

    assert not sorted(codes - set(LANGUAGE_NAMES_EN))


def test_language_code_source_matches_the_precedence_rule(typed_graph, iana_records):
    """IANA unless ours extends IANA's tag; derived only when IANA has none."""
    checked = 0
    for tld, entry in typed_graph.tlds.items():
        annotations = entry.get("annotations", {})
        source = annotations.get("language_code_source")
        if source is None:
            assert "language_code" not in annotations, tld
            continue
        checked += 1
        code = annotations["language_code"]
        iana_code = iana_records[tld].language_code
        if source == "IANA":
            assert code == iana_code, tld
        elif source == "refined":
            assert iana_code and code.startswith(f"{iana_code}-"), tld
        else:
            assert source == "derived" and iana_code is None, tld
    assert checked, "no built TLD carries language_code_source"


# --- RDAP ---


def test_no_record_has_more_than_one_distinct_rdap_base_url(iana_records):
    """The build fails on this; tlds.json models one rdap_server per TLD."""
    several = {
        name: record.rdap_base_urls
        for name, record in iana_records.items()
        if len(set(record.rdap_base_urls)) > 1
    }

    assert not several


def test_supplemental_rdap_does_not_overlap_with_iana_tlds_json(iana_records):
    """A supplemental entry IANA now publishes is shadowed and should be removed."""
    supplemental = set(parse_supplemental_cctld_rdap())
    assert supplemental, "supplemental RDAP file has no entries"

    published = {name for name, r in iana_records.items() if r.rdap_base_urls}

    assert not sorted(supplemental & published)


# --- Archive seed ---


def test_archive_seed_keys_are_known_tlds(iana_records):
    seed = parse_tld_archive()
    assert seed, "the archive seed is empty"

    assert not sorted(set(seed) - set(iana_records))


# The seed is frozen. An entry leaves only when IANA drops the TLD, and these
# counts change with it, deliberately.
SEEDED_TLD_CREATED = 1590
SEEDED_ARCHIVED_IANA_TAGS = {
    "aero": "sponsored",
    "arpa": "infrastructure",
    "asia": "sponsored",
    "biz": "generic-restricted",
    "cat": "sponsored",
    "coop": "sponsored",
    "edu": "sponsored",
    "gov": "sponsored",
    "int": "sponsored",
    "jobs": "sponsored",
    "mil": "sponsored",
    "museum": "sponsored",
    "name": "generic-restricted",
    "post": "sponsored",
    "pro": "generic-restricted",
    "tel": "sponsored",
    "travel": "sponsored",
    "xxx": "sponsored",
}


def test_archive_seed_has_lost_no_entry():
    """A deleted entry silently drops tld_created, which no live source restores."""
    seed = parse_tld_archive()

    assert sum("tld_created" in entry for entry in seed.values()) == SEEDED_TLD_CREATED
    assert {
        tld: entry["archived"]["iana_tag"]["value"]
        for tld, entry in seed.items()
        if "archived" in entry
    } == SEEDED_ARCHIVED_IANA_TAGS


def test_archived_iana_tag_differs_from_the_current_tag(iana_records):
    """An archived value IANA publishes again is live, not archived."""
    archived = {
        tld: entry["archived"]["iana_tag"]["value"]
        for tld, entry in parse_tld_archive().items()
        if "iana_tag" in entry.get("archived", {})
    }
    assert set(archived.values()) == ARCHIVED_IANA_TAGS

    assert not {
        tld: value for tld, value in archived.items() if iana_records[tld].type == value
    }


def test_archive_seed_reaches_the_built_graph(typed_graph):
    """Every seed value is published: tld_created at the top level, tags under archived."""
    seed = parse_tld_archive()

    for tld, entry in seed.items():
        built = typed_graph.tlds[tld]
        assert built.get("tld_created") == entry.get("tld_created"), tld
        assert built.get("archived") == entry.get("archived"), tld
    unseeded = set(typed_graph.tlds) - set(seed)
    assert not [t for t in unseeded if "tld_created" in typed_graph.tlds[t]]


# --- Dropped records ---


def test_never_delegated_names_absent_from_iana_are_absent_everywhere(typed_graph):
    """emerson and xn--4gq48lf9j left the IANA data, so they leave every artifact."""
    dropped = {"emerson", "xn--4gq48lf9j"}

    assert not dropped & set(typed_graph.tlds)
    listed = {tld for a in typed_graph.agreements["agreements"] for tld in a["tlds"]}
    assert not dropped & listed
