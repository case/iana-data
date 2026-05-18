"""Integration tests for TLD build process."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _pytest.monkeypatch import MonkeyPatch

from src.build.tlds import OutputPaths, build_tlds_json
from src.parse.rdap_json import parse_rdap_json
from src.parse.root_db_html import parse_root_db_html
from src.parse.tech_aliases import parse_tech_aliases

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
    )
    result = build_tlds_json(paths)
    yield SimpleNamespace(
        tlds_json=paths.tlds_json,
        tlds_index=paths.tlds_index,
        tld_dir=paths.tld_dir,
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
        else:
            assert derived_type == "gtld"


def test_build_tlds_json_delegated_status(shared_build):
    """delegated TLDs have orgs with tld_manager."""
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    for tld_entry in data["tlds"]:
        if tld_entry["delegated"]:
            assert "orgs" in tld_entry
            assert "tld_manager" in tld_entry["orgs"]


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


def test_build_tlds_json_tech_alias_annotation(shared_build):
    """TLDs whose orgs.tech matches data/manual/tech-aliases.json get annotations.tech_alias.

    Picks a TLD known to have 'Identity Digital Limited' as orgs.tech in
    current source data and asserts the canonical alias is set.
    """
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    tld_map = {entry["tld"]: entry for entry in data["tlds"]}

    id_aliased = [
        entry
        for entry in data["tlds"]
        if entry.get("annotations", {}).get("tech_alias") == "Identity Digital"
    ]
    assert id_aliased, "Expected at least one TLD with tech_alias='Identity Digital'"

    id_raw_names = {
        "Identity Digital Limited",
        "Identity Digital Inc.",
        "Identity Digital Limited c/o Identity Digital Inc.",
        "Afilias",
        "Afilias Limited",
        "Donuts Inc",
        "Internet Computer Bureau Ltd",
        "Internet Computer Bureau Limited",
    }
    for entry in id_aliased:
        tech = entry.get("orgs", {}).get("tech")
        assert tech in id_raw_names, (
            f"{entry['tld']} has tech_alias='Identity Digital' but unexpected orgs.tech={tech!r}"
        )

    abbott = tld_map.get("abbott")
    if abbott and abbott.get("orgs", {}).get("tech") == "Identity Digital Limited":
        assert abbott["annotations"]["tech_alias"] == "Identity Digital"


def test_build_tlds_json_tech_alias_only_set_for_known_aliases(shared_build):
    """A TLD gets annotations.tech_alias iff its orgs.tech is in tech-aliases.json.

    Guards against regressions where the alias is set for every TLD,
    hardcoded, or omitted when it should be present.
    """
    with open(shared_build.tlds_json) as f:
        data = json.load(f)

    tech_aliases = parse_tech_aliases()

    for entry in data["tlds"]:
        tech = entry.get("orgs", {}).get("tech")
        actual_alias = entry.get("annotations", {}).get("tech_alias")
        if tech and tech in tech_aliases:
            assert actual_alias == tech_aliases[tech], (
                f"{entry['tld']}: orgs.tech={tech!r} should alias to "
                f"{tech_aliases[tech]!r}, got {actual_alias!r}"
            )
        else:
            assert actual_alias is None, (
                f"{entry['tld']}: orgs.tech={tech!r} is not in tech-aliases.json "
                f"but has annotations.tech_alias={actual_alias!r}"
            )


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
