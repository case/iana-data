"""Integration tests for TLD build process."""

import html
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _pytest.monkeypatch import MonkeyPatch

from src.build.tlds import OutputPaths, build_tlds_json
from src.parse.rdap_json import parse_rdap_json
from src.parse.root_db_html import parse_root_db_html

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


@pytest.fixture
def temp_output(tmp_path, monkeypatch):
    """Function-scoped OutputPaths under tmp_path.

    Tests that need fresh state per invocation (idempotency, cold-start,
    injected write errors) use this fixture and pass it to build_tlds_json.
    """
    monkeypatch.setattr(
        "src.utilities.metadata.METADATA_FILE", str(tmp_path / "metadata.json")
    )
    return OutputPaths(
        tlds_json=tmp_path / "tlds.json",
        tlds_index=tmp_path / "tlds-index.json",
        tld_dir=tmp_path / "tld",
        organizations_json=tmp_path / "organizations.json",
        places_json=tmp_path / "places.json",
        cultures_json=tmp_path / "cultures.json",
        agreements_json=tmp_path / "agreements.json",
    )


@pytest.fixture(scope="module")
def shared_build(tmp_path_factory):
    """Module-scoped single build of all outputs, reused by read-only tests.

    build_tlds_json writes 1596 files per call. Sharing one build across
    all read-only inspection tests in this module cuts test-file runtime
    roughly by the number of read-only tests.
    """
    tmp = tmp_path_factory.mktemp("shared_build")
    mp = MonkeyPatch()
    mp.setattr("src.utilities.metadata.METADATA_FILE", str(tmp / "metadata.json"))
    paths = OutputPaths(
        tlds_json=tmp / "tlds.json",
        tlds_index=tmp / "tlds-index.json",
        tld_dir=tmp / "tld",
        organizations_json=tmp / "organizations.json",
        places_json=tmp / "places.json",
        cultures_json=tmp / "cultures.json",
        agreements_json=tmp / "agreements.json",
    )
    result = build_tlds_json(paths)
    yield SimpleNamespace(
        tlds_json=paths.tlds_json,
        tlds_index=paths.tlds_index,
        tld_dir=paths.tld_dir,
        organizations_json=paths.organizations_json,
        result=result,
    )
    mp.undo()


def test_build_tlds_json_creates_file(shared_build):
    """build_tlds_json returns the expected result keys and writes tlds.json."""
    assert "total_tlds" in shared_build.result
    assert "output_file" in shared_build.result
    assert shared_build.tlds_json.exists()


def test_build_tlds_json_has_correct_structure(shared_build):
    """tlds.json has the expected top-level structure."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    assert "description" in data
    assert "publication" in data
    assert "sources" in data
    assert "tlds" in data
    assert "iana_root_db" in data["sources"]
    assert "iana_rdap" in data["sources"]
    assert isinstance(data["tlds"], list)


def test_build_tlds_json_tld_count_matches_source(shared_build):
    """Number of TLDs in output matches root zone source."""
    root_zone_entries = parse_root_db_html()
    expected_count = len(root_zone_entries)

    assert shared_build.result["total_tlds"] == expected_count

    with open(shared_build.tlds_json) as f:
        data = json.load(f)
    assert len(data["tlds"]) == expected_count


def test_build_tlds_json_has_required_fields(shared_build):
    """Every TLD entry has required fields."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    required_keys = {"tld", "delegated", "iana_tag", "type"}
    for i, tld_entry in enumerate(data["tlds"]):
        missing = required_keys - tld_entry.keys()
        assert not missing, (
            f"Entry {i} ({tld_entry.get('tld', '<no tld>')}) missing keys: {missing}"
        )


def test_build_tlds_json_strips_leading_dots(shared_build):
    """TLDs in output don't have leading dots."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    for tld_entry in data["tlds"]:
        assert not tld_entry["tld"].startswith(".")


def test_build_tlds_json_derives_type_correctly(shared_build):
    """type field is correctly derived from iana_tag."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    for tld_entry in data["tlds"]:
        iana_tag = tld_entry["iana_tag"]
        derived_type = tld_entry["type"]

        if iana_tag == "country-code":
            assert derived_type == "cctld"
        elif iana_tag == "infrastructure":
            assert derived_type == "infrastructure"
        else:
            assert derived_type == "gtld"


def test_build_tlds_json_arpa_is_infrastructure_type(shared_build):
    """.arpa is the lone infrastructure TLD and is typed as such, not gtld."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    arpa = {e["tld"]: e for e in data["tlds"]}["arpa"]

    assert arpa["iana_tag"] == "infrastructure"
    assert arpa["type"] == "infrastructure"


def test_build_tlds_json_delegated_status(shared_build):
    """delegated TLDs have orgs.iana with a sponsor."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    for tld_entry in data["tlds"]:
        if tld_entry["delegated"]:
            assert "orgs" in tld_entry
            assert "sponsor" in tld_entry["orgs"]["iana"]


def test_build_tlds_json_rdap_servers_present(shared_build):
    """RDAP servers are included for TLDs that have them."""
    rdap_lookup = parse_rdap_json()

    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    tld_map = {entry["tld"]: entry for entry in data["tlds"]}

    for tld in list(rdap_lookup.keys())[:5]:
        if tld in tld_map:
            entry = tld_map[tld]
            assert "rdap_server" in entry
            assert "annotations" in entry
            assert "rdap_source" in entry["annotations"]


def test_build_tlds_json_idn_unicode_field(shared_build):
    """IDN TLDs have a tld_unicode field whose value isn't the A-label."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    idn_tlds = [entry for entry in data["tlds"] if entry["tld"].startswith("xn--")]

    if idn_tlds:
        idn_with_unicode = [e for e in idn_tlds if "tld_unicode" in e]
        assert len(idn_with_unicode) > 0

        for entry in idn_with_unicode:
            assert entry["tld_unicode"] != entry["tld"]
            assert not entry["tld_unicode"].startswith("xn--")


def test_build_tlds_json_publication_timestamp_format(shared_build):
    """publication timestamp uses YYYY-MM-DDTHH:MM:SSZ (no microseconds)."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    publication = data["publication"]
    assert publication.endswith("Z")
    assert "." not in publication
    assert len(publication) == 20


def test_build_tlds_json_delegated_count_matches_root_db(shared_build):
    """Delegated TLD count matches root zone DB assigned entries."""
    root_zone_entries = parse_root_db_html()
    expected_delegated_count = sum(
        1 for entry in root_zone_entries if entry["manager"] != "Not assigned"
    )

    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    delegated_tlds = [entry for entry in data["tlds"] if entry["delegated"]]
    assert len(delegated_tlds) == expected_delegated_count


def test_build_tlds_json_ascii_cctld_has_country_name(shared_build):
    """ASCII ccTLDs have country_name_iso in annotations."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    tld_map = {entry["tld"]: entry for entry in data["tlds"]}

    test_cctlds = {
        "us": "United States",
        "gb": "United Kingdom",
        "de": "Germany",
        "jp": "Japan",
        "fr": "France",
    }

    for cctld, expected_name in test_cctlds.items():
        assert cctld in tld_map
        entry = tld_map[cctld]
        assert "annotations" in entry
        assert "country_name_iso" in entry["annotations"]
        assert entry["annotations"]["country_name_iso"] == expected_name


def test_build_tlds_json_idn_cctld_has_country_name(shared_build):
    """IDN ccTLDs have country_name_iso in annotations."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    idn_cctlds = [entry for entry in data["tlds"] if "tld_iso" in entry]
    assert len(idn_cctlds) > 0, "Should have at least some IDN ccTLDs"

    for entry in idn_cctlds:
        assert "annotations" in entry
        assert "country_name_iso" in entry["annotations"]
        assert isinstance(entry["annotations"]["country_name_iso"], str)
        assert len(entry["annotations"]["country_name_iso"]) > 0


def test_build_tlds_json_cctld_overrides(shared_build):
    """ccTLD overrides (ac, eu, su, uk) have correct country names."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    tld_map = {entry["tld"]: entry for entry in data["tlds"]}

    overrides = {
        "ac": "Ascension Island",
        "eu": "European Union",
        "su": "Soviet Union",
        "uk": "United Kingdom",
    }

    for cctld, expected_name in overrides.items():
        if cctld in tld_map:
            entry = tld_map[cctld]
            assert "annotations" in entry
            assert "country_name_iso" in entry["annotations"]
            assert entry["annotations"]["country_name_iso"] == expected_name


def test_build_tlds_json_orgs_iana_populated(shared_build):
    """orgs.iana.{sponsor,admin,tech} carries the IANA per-TLD roles."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    iana = {e["tld"]: e for e in data["tlds"]}["bestbuy"]["orgs"]["iana"]

    assert iana["sponsor"] == "BBY Solutions, Inc."
    assert iana["admin"]
    assert iana["tech"]


def test_build_tlds_json_orgs_flat_fields_removed(shared_build):
    """The legacy flat orgs.{tld_manager,admin,tech} fields are gone; only the
    nested orgs.iana / orgs.icann form remains."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    orgs = {e["tld"]: e for e in data["tlds"]}["bestbuy"]["orgs"]

    assert "tld_manager" not in orgs
    assert "admin" not in orgs
    assert "tech" not in orgs
    assert "iana" in orgs


def test_build_tlds_json_no_html_entities_in_any_field(shared_build):
    """No HTML entity (e.g. &amp;) survives into any generated string field.

    End-to-end guard for the Extract-faithful / Transform-decodes policy: every
    field the parser extracts from HTML (orgs, registry_url, whois/rdap, etc.)
    must carry a literal '&', never '&amp;'. unescape(v) != v flags a real
    entity; a bare '&' (e.g. "AT&T") is left unchanged.
    """
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from strings(value)
        elif isinstance(node, list):
            for item in node:
                yield from strings(item)

    offenders = [
        (entry["tld"], value)
        for entry in data["tlds"]
        for value in strings(entry)
        if html.unescape(value) != value
    ]

    assert not offenders, f"HTML entities leaked into generated data: {offenders[:10]}"


def test_build_tlds_json_orgs_icann_populated_for_gtld(shared_build):
    """gTLDs carry orgs.icann.* from the ICANN gTLDs report."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    icann = {e["tld"]: e for e in data["tlds"]}["bestbuy"]["orgs"]["icann"]

    assert icann["registry_operator"] == "BBY Solutions, Inc."
    assert icann["specification_13"] is True
    assert icann["contract_terminated"] is False
    assert icann["date_delegated"] == "2016-07-19"


def test_build_tlds_json_orgs_icann_absent_for_cctld(shared_build):
    """ccTLDs are not in the ICANN gTLDs report, so they have no orgs.icann."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    orgs = {e["tld"]: e for e in data["tlds"]}["de"]["orgs"]

    assert "icann" not in orgs
    assert "iana" in orgs  # IANA roles still present for ccTLDs


def test_build_tlds_json_icann_translation_annotation(shared_build):
    """IDN gTLDs carry ICANN's raw Translation as annotations.icann_translation_en."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    entry = {e["tld"]: e for e in data["tlds"]}["xn--1ck2e1b"]  # セール

    assert entry["annotations"]["icann_translation_en"] == "sale"


def test_build_tlds_json_geographic_scope_and_culture_for_gtld(shared_build):
    """A geographic+cultural gTLD carries both editorial annotations."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    annotations = {e["tld"]: e for e in data["tlds"]}["eus"]["annotations"]

    assert annotations["geographic_scope"] == "subdivision"
    assert annotations["cultural_affiliation"] == "basque"


def test_build_tlds_json_city_gtld_scope(shared_build):
    """A city gTLD carries geographic_scope 'city'."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    assert {e["tld"]: e for e in data["tlds"]}["amsterdam"]["annotations"][
        "geographic_scope"
    ] == "city"


def test_build_tlds_json_cultural_only_gtld_has_no_scope(shared_build):
    """A culture-only gTLD (no place parent) has cultural_affiliation but no scope."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    annotations = {e["tld"]: e for e in data["tlds"]}["arab"]["annotations"]

    assert annotations["cultural_affiliation"] == "arab"
    assert "geographic_scope" not in annotations


def test_build_tlds_json_cctld_geographic_scope_derived_country(shared_build):
    """ccTLDs get geographic_scope 'country' derived in the build, not from the file."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    assert {e["tld"]: e for e in data["tlds"]}["de"]["annotations"][
        "geographic_scope"
    ] == "country"


def test_build_tlds_json_eu_scope_overrides_country_default(shared_build):
    """.eu is a country-code TLD but the manual file overrides its scope to supranational."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    assert {e["tld"]: e for e in data["tlds"]}["eu"]["annotations"][
        "geographic_scope"
    ] == "supranational"


def test_build_tlds_json_plain_gtld_has_no_editorial_scope(shared_build):
    """A non-geographic, non-cultural gTLD carries neither editorial annotation."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    annotations = {e["tld"]: e for e in data["tlds"]}["com"].get("annotations", {})

    assert "geographic_scope" not in annotations
    assert "cultural_affiliation" not in annotations


def test_build_tlds_json_gtld_no_country_name(shared_build):
    """gTLDs do not have country_name_iso."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    gtlds = [entry for entry in data["tlds"] if entry["type"] == "gtld"]

    gtld_tlds = [e["tld"] for e in gtlds]
    test_gtlds = ["com", "org", "net", "info", "biz"]

    for gtld in test_gtlds:
        if gtld in gtld_tlds:
            entry = [e for e in gtlds if e["tld"] == gtld][0]
            if "annotations" in entry:
                assert "country_name_iso" not in entry["annotations"]


def test_build_tlds_json_org_annotations_use_alias_and_slug(shared_build):
    """Resolved registry orgs get both a display-name alias and a slug FK;
    the retired flat alias keys are gone everywhere."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    id_tlds = [
        entry
        for entry in data["tlds"]
        if entry.get("annotations", {}).get("iana_tech_slug") == "identity-digital"
    ]
    assert id_tlds, "expected TLDs whose tech operator resolves to identity-digital"
    for entry in id_tlds:
        assert entry["annotations"]["iana_tech_alias"] == "Identity Digital"

    for entry in data["tlds"]:
        annotations = entry.get("annotations", {})
        assert "tech_alias" not in annotations
        assert "tld_manager_alias" not in annotations


def test_build_does_not_rewrite_iptoasn_metadata(temp_output, tmp_path):
    """Build loads iptoasn data but must not touch metadata.json; the download
    step owns IPTOASN.last_downloaded."""
    metadata_path = tmp_path / "metadata.json"
    sentinel = {"IPTOASN": {"last_downloaded": "2020-01-01T00:00:00Z"}}
    metadata_path.write_text(json.dumps(sentinel))

    build_tlds_json(temp_output)

    assert json.loads(metadata_path.read_text()) == sentinel


def test_per_tld_files_exist(shared_build):
    """Per-TLD files are written for known TLDs."""
    for slug in ("com", "uk", "aaa"):
        path = shared_build.tld_dir / f"{slug}.json"
        assert path.exists(), f"{path} missing"


def test_per_tld_file_count_matches_tlds_json(shared_build):
    """One per-TLD file per entry in tlds.json."""
    with open(shared_build.tlds_json) as f:
        tlds_json = json.load(f)

    file_count = len(list(shared_build.tld_dir.glob("*.json")))
    assert file_count == len(tlds_json["tlds"])


def test_idn_filename_uses_a_label(shared_build):
    """IDN per-TLD files are named by A-label, not U-label."""
    with open(shared_build.tlds_json) as f:
        tlds_json = json.load(f)

    idn_entries = [e for e in tlds_json["tlds"] if e["tld"].startswith("xn--")]
    assert idn_entries, "Expected at least one IDN TLD in source data"

    for entry in idn_entries:
        a_label_file = shared_build.tld_dir / f"{entry['tld']}.json"
        assert a_label_file.exists(), f"Missing A-label file {a_label_file}"
        if "tld_unicode" in entry:
            u_label_file = shared_build.tld_dir / f"{entry['tld_unicode']}.json"
            assert not u_label_file.exists(), (
                f"U-label file should not exist: {u_label_file}"
            )


def test_per_tld_file_content_matches_tlds_json(shared_build):
    """Per-TLD file 'tld' key deep-equals the corresponding entry in tlds.json."""
    with open(shared_build.tlds_json) as f:
        tlds_json = json.load(f)

    by_slug = {entry["tld"]: entry for entry in tlds_json["tlds"]}

    # Sample a mix: common gTLDs, a ccTLD, an IDN.
    # Sort the IDN candidates so the test picks the same one each run.
    sample_slugs = ["com", "uk", "aaa"]
    idn_slugs = sorted(s for s in by_slug if s.startswith("xn--"))
    if idn_slugs:
        sample_slugs.append(idn_slugs[0])

    for slug in sample_slugs:
        if slug not in by_slug:
            continue
        with open(shared_build.tld_dir / f"{slug}.json") as f:
            per_tld = json.load(f)
        assert per_tld["tld"] == by_slug[slug]


def test_per_tld_file_is_self_contained(shared_build):
    """Each per-TLD file carries publication and sources alongside the TLD record."""
    with open(shared_build.tld_dir / "com.json") as f:
        per_tld = json.load(f)

    assert "publication" in per_tld
    assert "sources" in per_tld
    assert "tld" in per_tld
    assert "iana_root_db" in per_tld["sources"]
    assert "iana_rdap" in per_tld["sources"]


def test_per_tld_file_publication_matches_tlds_json(shared_build):
    """All artifacts share the same publication timestamp from one build."""
    with open(shared_build.tlds_json) as f:
        bulk_publication = json.load(f)["publication"]
    with open(shared_build.tlds_index) as f:
        index_publication = json.load(f)["publication"]
    with open(shared_build.tld_dir / "com.json") as f:
        per_tld_publication = json.load(f)["publication"]

    assert bulk_publication == index_publication == per_tld_publication


def test_index_has_one_entry_per_tld(shared_build):
    """Index lists every TLD exactly once and count agrees."""
    with open(shared_build.tlds_json) as f:
        tlds_json = json.load(f)
    with open(shared_build.tlds_index) as f:
        index = json.load(f)

    assert len(index["tlds"]) == len(tlds_json["tlds"])
    assert index["count"] == len(index["tlds"])

    bulk_slugs = {entry["tld"] for entry in tlds_json["tlds"]}
    index_slugs = {entry["tld"] for entry in index["tlds"]}
    assert bulk_slugs == index_slugs


def test_index_entry_shape(shared_build):
    """Index entries have only the documented fields; tld_unicode is conditional on IDN."""
    with open(shared_build.tlds_index) as f:
        index = json.load(f)

    by_slug = {entry["tld"]: entry for entry in index["tlds"]}

    optional_fields = {"tld_unicode", "tld_created", "tld_updated"}
    required_fields = {"tld", "type", "delegated"}
    allowed = required_fields | optional_fields

    for entry in index["tlds"]:
        assert required_fields.issubset(entry.keys()), (
            f"Missing required fields in {entry}"
        )
        extra = set(entry.keys()) - allowed
        assert not extra, f"Unexpected fields {extra} in {entry}"

    idn_slug = next((s for s in by_slug if s.startswith("xn--")), None)
    assert idn_slug, "Expected at least one IDN TLD in index"
    assert "tld_unicode" in by_slug[idn_slug]
    assert not by_slug[idn_slug]["tld_unicode"].startswith("xn--")

    assert "com" in by_slug
    assert "tld_unicode" not in by_slug["com"]


def test_empty_tld_dir_recovery(temp_output):
    """Build populates tld_dir from scratch when it doesn't exist (cold start)."""
    assert not temp_output.tld_dir.exists()

    build_tlds_json(temp_output)

    assert temp_output.tld_dir.is_dir()
    files = list(temp_output.tld_dir.glob("*.json"))
    assert len(files) > 0


def test_build_aborts_index_when_per_tld_write_fails(temp_output, monkeypatch):
    """If a per-TLD write errors, the index is not written and the build returns an error.

    Guards the canonical-data invariant: the index never references a TLD
    whose per-TLD file failed to write. The test injects an error for one
    specific slug and asserts the index file was not created.
    """
    import src.build.tlds as tlds_module

    real_write = tlds_module.write_json_if_changed
    failing_slug = "com"

    def flaky_write(filepath, data, **kwargs):
        if str(filepath).endswith(f"/{failing_slug}.json"):
            return (False, "error")
        return real_write(filepath, data, **kwargs)

    monkeypatch.setattr(tlds_module, "write_json_if_changed", flaky_write)

    result = build_tlds_json(temp_output)

    assert "error" in result, f"Expected error in result, got {result}"
    assert failing_slug in result["error"] or "per-TLD" in result["error"]
    assert not temp_output.tlds_index.exists(), (
        "Index was written despite a per-TLD write failure"
    )


def test_idempotent_second_run(temp_output):
    """A second build with the same source data rewrites zero per-TLD files.

    Verifies that write_json_if_changed's exclude_fields=["publication"]
    actually suppresses writes when only the timestamp would change.
    """
    build_tlds_json(temp_output)
    mtimes_before = {
        p: p.stat().st_mtime_ns for p in temp_output.tld_dir.glob("*.json")
    }
    index_mtime_before = temp_output.tlds_index.stat().st_mtime_ns

    build_tlds_json(temp_output)
    mtimes_after = {p: p.stat().st_mtime_ns for p in temp_output.tld_dir.glob("*.json")}
    index_mtime_after = temp_output.tlds_index.stat().st_mtime_ns

    assert mtimes_before.keys() == mtimes_after.keys(), "File set changed between runs"
    unchanged = [p for p in mtimes_before if mtimes_before[p] == mtimes_after[p]]
    assert len(unchanged) == len(mtimes_before), (
        f"{len(mtimes_before) - len(unchanged)} per-TLD files were rewritten on a no-op second run"
    )
    assert index_mtime_before == index_mtime_after, (
        "Index was rewritten on a no-op second run"
    )
