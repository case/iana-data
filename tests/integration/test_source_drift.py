"""Tests for detecting drift between IANA source publications.

IANA publishes TLD data in two places that update on different schedules:
- TLD JSON (https://data.iana.org/TLD/v1/tlds.json). The Root Zone Database
  export, and the authoritative source for delegation.
- TLD list (https://data.iana.org/TLD/tlds-alpha-by-domain.txt). A flat
  text file of delegated TLDs.

When a TLD gets newly delegated (or undelegated), one source may update
before the other. These tests detect that drift and report it clearly.
"""

import warnings
from pathlib import Path

import pytest

from src.config import SOURCE_DIR, SOURCE_FILES
from src.parse.iana_tlds_json import load_iana_tlds
from src.parse.tlds_txt import parse_tlds_txt
from tests.dated_fixtures import latest_fixture

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


def _compute_drift(iana_tlds_path: Path, tlds_txt_path: Path) -> dict:
    """Compute drift between the IANA TLD JSON and tlds.txt.

    Returns a dict with:
        delegated_in_iana_tlds: set of TLDs with status "active" in the JSON
        listed_in_tlds_txt: set of TLDs in tlds.txt
        in_iana_tlds_only: TLDs active in the JSON but missing from tlds.txt
        in_tlds_txt_only: TLDs in tlds.txt but not active in the JSON
    """
    delegated_in_iana_tlds = {
        record.name
        for record in load_iana_tlds(iana_tlds_path)
        if record.status == "active"
    }

    tlds_txt_list = parse_tlds_txt(tlds_txt_path)
    listed_in_tlds_txt = {tld.lower() for tld in tlds_txt_list}

    return {
        "delegated_in_iana_tlds": delegated_in_iana_tlds,
        "listed_in_tlds_txt": listed_in_tlds_txt,
        "in_iana_tlds_only": delegated_in_iana_tlds - listed_in_tlds_txt,
        "in_tlds_txt_only": listed_in_tlds_txt - delegated_in_iana_tlds,
    }


# --- Fixture-based unit tests ---


class TestDriftDetectionWithFixtures:
    """Verify drift detection logic using controlled fixture data."""

    def test_no_drift_with_consistent_fixtures(self):
        """When both sources agree, no drift should be detected."""
        drift = _compute_drift(
            latest_fixture(FIXTURES_DIR, "iana-tlds.json"),
            FIXTURES_DIR / "tlds.txt",
        )
        # tlds.txt lists names (XBOX, XYZ) the trimmed JSON fixture omits.
        # The reverse must not happen: no active JSON name is missing from it.
        assert drift["delegated_in_iana_tlds"], "fixture has no active TLDs"
        assert len(drift["in_iana_tlds_only"]) == 0, (
            f"Consistent fixtures should have no JSON-only drift, "
            f"but found: {sorted(drift['in_iana_tlds_only'])}"
        )

    def test_detects_tlds_txt_lagging_behind_iana_tlds(self):
        """When the JSON has a newly delegated TLD not yet in tlds.txt."""
        drift = _compute_drift(
            latest_fixture(FIXTURES_DIR, "iana-tlds.json"),
            FIXTURES_DIR / "tlds-drift-behind.txt",
        )
        # ACO is active in the JSON fixture but intentionally omitted from
        # tlds-drift-behind.txt
        assert drift["in_iana_tlds_only"] == {"aco"}

    def test_retired_and_reserved_records_are_not_delegated(self):
        """Only status "active" counts; a retired name in tlds.txt is txt-only drift."""
        drift = _compute_drift(
            latest_fixture(FIXTURES_DIR, "iana-tlds.json"),
            FIXTURES_DIR / "tlds.txt",
        )

        assert (
            not {"abarth", "bl", "local", "yu", "xn--0zwm56d"}
            & (drift["delegated_in_iana_tlds"])
        )

    def test_drift_computation_returns_correct_sets(self):
        """Verify the drift computation returns well-formed results."""
        drift = _compute_drift(
            latest_fixture(FIXTURES_DIR, "iana-tlds.json"),
            FIXTURES_DIR / "tlds-drift-behind.txt",
        )
        # Sets should be non-overlapping subsets
        assert not (drift["in_iana_tlds_only"] & drift["in_tlds_txt_only"])
        # All JSON-only items should be in delegated_in_iana_tlds
        assert drift["in_iana_tlds_only"] <= drift["delegated_in_iana_tlds"]
        # All tlds_txt_only items should be in listed_in_tlds_txt
        assert drift["in_tlds_txt_only"] <= drift["listed_in_tlds_txt"]


# --- Production data drift monitoring ---


def test_source_drift_warning():
    """Detect and warn about drift between the IANA TLD JSON and tlds.txt.

    This test does NOT fail on drift. It issues warnings so the drift
    is visible in test output without blocking the pipeline. The build
    uses the JSON as its source of truth, so drift in tlds.txt is
    expected and temporary.
    """
    iana_tlds_path = Path(SOURCE_DIR) / SOURCE_FILES["IANA_TLDS"]
    tlds_txt_path = Path(SOURCE_DIR) / SOURCE_FILES["TLD_LIST"]

    if not iana_tlds_path.exists() or not tlds_txt_path.exists():
        pytest.skip("Source data files not available")

    drift = _compute_drift(iana_tlds_path, tlds_txt_path)

    if drift["in_iana_tlds_only"]:
        warnings.warn(
            f"IANA source drift: {len(drift['in_iana_tlds_only'])} TLD(s) active "
            f"in the IANA TLD JSON but not yet in tlds.txt: "
            f"{sorted(drift['in_iana_tlds_only'])}",
            stacklevel=1,
        )

    if drift["in_tlds_txt_only"]:
        warnings.warn(
            f"IANA source drift: {len(drift['in_tlds_txt_only'])} TLD(s) in "
            f"tlds.txt but not active in the IANA TLD JSON: "
            f"{sorted(drift['in_tlds_txt_only'])}",
            stacklevel=1,
        )
