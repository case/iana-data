"""Cross-source reconciliation of the built tlds.json.

These tests assert that the shipped tlds.json is consistent with the
authoritative IANA source for each field. Per the .merck drift incident
(commit 9a2c1b9, March 2026), we follow per-field source-of-truth:

- Root DB (iana-root.html) is authoritative for the TLD set, delegation
  status, manager, and type.
- IANA RDAP bootstrap is authoritative for gTLD RDAP server URLs.
- iana-tlds.txt is advisory only; it drifts from root DB in normal
  operation. test_source_drift.py surfaces the drift as warnings; the
  build must not depend on it.

These tests prefer the committed data/generated/tlds.json artifact when
present so CI catches corruption in the file that would actually ship,
not just in live build logic. On a fresh checkout the fixture builds
into a tmp dir so the safeguard still runs.
"""

import ast
import inspect
import json
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch

import src.build.tlds as build_module
from src.build.tlds import OutputPaths, build_tlds_json
from src.config import TLDS_OUTPUT_FILE
from src.parse.rdap_json import parse_rdap_json
from src.parse.root_db_html import parse_root_db_html


@pytest.fixture(scope="module")
def tlds_data(tmp_path_factory):
    """Return parsed tlds.json: prefer committed artifact, else build fresh.

    Normal operation: the committed data/generated/tlds.json always exists,
    so the build-fresh branch is exercised only on fresh checkouts that
    haven't been built yet. It is intentionally kept rather than replaced
    with pytest.skip so the safeguard runs even in that case.
    """
    committed = Path(TLDS_OUTPUT_FILE)
    if committed.exists():
        with open(committed) as f:
            return json.load(f)

    tmp = tmp_path_factory.mktemp("reconciliation_build")
    mp = MonkeyPatch()
    mp.setattr("src.utilities.metadata.METADATA_FILE", str(tmp / "metadata.json"))
    paths = OutputPaths(
        tlds_json=tmp / "tlds.json",
        tlds_index=tmp / "tlds-index.json",
        tld_dir=tmp / "tld",
        organizations_json=tmp / "organizations.json",
    )
    try:
        build_tlds_json(paths)
        with open(paths.tlds_json) as f:
            return json.load(f)
    finally:
        mp.undo()


def test_built_tlds_set_equals_root_db_set(tlds_data):
    """Every TLD in root DB is in tlds.json and nothing extra.

    Stronger than count equality: catches the "drop entry X, duplicate
    entry Y, count unchanged" regression that count-based tests miss.

    Asserts against root DB only, not against tlds.txt or the union of
    sources, because per-field source-of-truth means tlds.txt drift is
    not a build error (see .merck incident, commit 9a2c1b9).
    """
    expected = {entry["domain"].lstrip(".").lower() for entry in parse_root_db_html()}
    actual = {entry["tld"].lower() for entry in tlds_data["tlds"]}

    missing = expected - actual
    extra = actual - expected
    assert not missing and not extra, (
        f"TLD set mismatch vs root DB. "
        f"Missing from tlds.json: {sorted(missing)}. "
        f"Extra in tlds.json: {sorted(extra)}."
    )


def test_built_rdap_entries_present_and_iana_sourced(tlds_data):
    """Every TLD in the IANA RDAP bootstrap appears in tlds.json with an IANA-sourced rdap_server.

    Does NOT exact-match URL strings because the build's source precedence
    is page_data > bootstrap > supplemental, and the two IANA sources can
    disagree on URL normalization (e.g., trailing slash). The invariants
    that actually matter: the TLD entry exists, rdap_server is populated,
    and annotations.rdap_source is "IANA" (not "supplemental").
    """
    rdap_lookup = parse_rdap_json()
    by_tld = {entry["tld"].lower(): entry for entry in tlds_data["tlds"]}

    missing_entries = []
    missing_rdap_server = []
    wrong_source = []
    for tld in rdap_lookup:
        entry = by_tld.get(tld.lower())
        if entry is None:
            missing_entries.append(tld)
            continue
        if not entry.get("rdap_server"):
            missing_rdap_server.append(tld)
        rdap_source = entry.get("annotations", {}).get("rdap_source")
        if rdap_source != "IANA":
            wrong_source.append((tld, rdap_source))

    assert not missing_entries and not missing_rdap_server and not wrong_source, (
        f"RDAP reconciliation failed. "
        f"Missing entries: {sorted(missing_entries)}. "
        f"Missing rdap_server: {sorted(missing_rdap_server)}. "
        f"Wrong rdap_source (first 5): {wrong_source[:5]}."
    )


def test_built_delegation_flag_matches_root_db(tlds_data):
    """For every TLD, delegated flag matches manager-not-not-assigned in root DB."""
    root_db_by_tld = {
        entry["domain"].lstrip(".").lower(): (entry["manager"] != "Not assigned")
        for entry in parse_root_db_html()
    }

    mismatches = []
    for entry in tlds_data["tlds"]:
        tld = entry["tld"].lower()
        if tld not in root_db_by_tld:
            continue
        expected_delegated = root_db_by_tld[tld]
        if entry["delegated"] != expected_delegated:
            mismatches.append((tld, entry["delegated"], expected_delegated))

    assert not mismatches, (
        f"delegated flag mismatch vs root DB for {len(mismatches)} TLD(s) "
        f"(first 5: {mismatches[:5]})"
    )


def test_built_tld_count_within_baseline_threshold(tlds_data):
    """Defend against systematic parser regression by comparing to a recorded baseline.

    All the other reconciliation tests above compare parse_root_db_html()
    against the built tlds.json. Both sides flow through the same parser,
    so a parser regression that silently shrinks the set (e.g., a regex
    change that fails to match some root-zone rows) would not be caught.
    Both sides shrink together and the cross-source equality still holds.

    This test guards against that by comparing the current TLD count
    against a baseline recorded inline below. The 5% threshold (~80 TLDs
    out of ~1594) is well above IANA's annual TLD growth rate. Update
    the baseline constants when a legitimate IANA expansion crosses the
    threshold (e.g., ICANN's next-round gTLD additions).
    """
    baseline_as_of = "2026-05-16"
    baseline_total = 1594
    baseline_delegated = 1437
    threshold = 0.05

    actual_total = len(tlds_data["tlds"])
    actual_delegated = sum(1 for e in tlds_data["tlds"] if e["delegated"])

    total_drift = abs(actual_total - baseline_total) / baseline_total
    delegated_drift = abs(actual_delegated - baseline_delegated) / baseline_delegated

    failures = []
    if total_drift >= threshold:
        failures.append(
            f"total TLD count drifted {total_drift:.1%} "
            f"(baseline {baseline_total} as of {baseline_as_of}, now {actual_total})"
        )
    if delegated_drift >= threshold:
        failures.append(
            f"delegated TLD count drifted {delegated_drift:.1%} "
            f"(baseline {baseline_delegated} as of {baseline_as_of}, now {actual_delegated})"
        )

    assert not failures, (
        f"TLD count outside baseline threshold ({threshold:.0%}): {failures}. "
        f"If this is legitimate IANA growth, update the baseline constants "
        f"in this test."
    )


def test_build_does_not_import_tlds_txt():
    """Architectural invariant: build must not depend on the tlds_txt module.

    tlds.txt drifts from root DB in normal operation (see .merck
    incident, commit 9a2c1b9, where the build was rewritten to derive
    delegation status from root DB alone). Re-introducing any tlds_txt
    module symbol into the build path would resurrect that
    drift-as-build-failure class of bug.

    Uses AST inspection rather than string grep so the check ignores
    occurrences of "tlds_txt" inside comments, docstrings, or unrelated
    identifiers.
    """
    tree = ast.parse(inspect.getsource(build_module))

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if "tlds_txt" in module or "tlds_txt" in alias.name:
                    violations.append(f"from {module} import {alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "tlds_txt" in alias.name:
                    violations.append(f"import {alias.name}")

    assert not violations, (
        f"src/build/tlds.py imports from tlds_txt module: {violations}. "
        "Per .merck incident (commit 9a2c1b9), build must derive TLD "
        "set membership from root DB alone."
    )
