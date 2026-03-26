"""Tests for detecting drift between IANA source publications.

IANA publishes TLD data in two places that update on different schedules:
- Root Zone DB (https://www.iana.org/domains/root/db) — HTML table with
  manager assignments. This is the authoritative source for delegation.
- TLD list (https://data.iana.org/TLD/tlds-alpha-by-domain.txt) — flat
  text file of delegated TLDs.

When a TLD gets newly delegated (or undelegated), one source may update
before the other. These tests detect that drift and report it clearly.
"""

import warnings
from pathlib import Path

import pytest

from src.config import SOURCE_DIR, SOURCE_FILES
from src.parse.root_db_html import parse_root_db_html
from src.parse.tlds_txt import parse_tlds_txt

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


def _compute_drift(root_db_path: Path, tlds_txt_path: Path) -> dict:
    """Compute drift between root DB and tlds.txt.

    Returns a dict with:
        delegated_in_root_db: set of TLDs delegated in root DB
        listed_in_tlds_txt: set of TLDs in tlds.txt
        in_root_db_only: TLDs delegated in root DB but missing from tlds.txt
        in_tlds_txt_only: TLDs in tlds.txt but not delegated in root DB
    """
    root_entries = parse_root_db_html(root_db_path)
    delegated_in_root_db = {
        entry["domain"].lstrip(".").lower()
        for entry in root_entries
        if entry["manager"] != "Not assigned"
    }

    tlds_txt_list = parse_tlds_txt(tlds_txt_path)
    listed_in_tlds_txt = {tld.lower() for tld in tlds_txt_list}

    return {
        "delegated_in_root_db": delegated_in_root_db,
        "listed_in_tlds_txt": listed_in_tlds_txt,
        "in_root_db_only": delegated_in_root_db - listed_in_tlds_txt,
        "in_tlds_txt_only": listed_in_tlds_txt - delegated_in_root_db,
    }


# --- Fixture-based unit tests ---


class TestDriftDetectionWithFixtures:
    """Verify drift detection logic using controlled fixture data."""

    def test_no_drift_with_consistent_fixtures(self):
        """When both sources agree, no drift should be detected."""
        drift = _compute_drift(
            FIXTURES_DIR / "root.html",
            FIXTURES_DIR / "tlds.txt",
        )
        # The tlds.txt fixture includes some TLDs (XBOX, XYZ) not in root.html
        # because the fixture is a subset of real data. But no TLD that's
        # delegated in root.html should be missing from tlds.txt.
        assert len(drift["in_root_db_only"]) == 0, (
            f"Consistent fixtures should have no root-DB-only drift, "
            f"but found: {sorted(drift['in_root_db_only'])}"
        )

    def test_detects_tlds_txt_lagging_behind_root_db(self):
        """When root DB has a newly delegated TLD not yet in tlds.txt."""
        drift = _compute_drift(
            FIXTURES_DIR / "root.html",
            FIXTURES_DIR / "tlds-drift-behind.txt",
        )
        # ACO is delegated in root.html but intentionally omitted from
        # tlds-drift-behind.txt
        assert "aco" in drift["in_root_db_only"], (
            f"Should detect 'aco' as delegated in root DB but missing from tlds.txt. "
            f"in_root_db_only: {sorted(drift['in_root_db_only'])}"
        )

    def test_drift_computation_returns_correct_sets(self):
        """Verify the drift computation returns well-formed results."""
        drift = _compute_drift(
            FIXTURES_DIR / "root.html",
            FIXTURES_DIR / "tlds-drift-behind.txt",
        )
        # Sets should be non-overlapping subsets
        assert not (drift["in_root_db_only"] & drift["in_tlds_txt_only"])
        # All root_db_only items should be in delegated_in_root_db
        assert drift["in_root_db_only"] <= drift["delegated_in_root_db"]
        # All tlds_txt_only items should be in listed_in_tlds_txt
        assert drift["in_tlds_txt_only"] <= drift["listed_in_tlds_txt"]


# --- Production data drift monitoring ---


def test_source_drift_warning():
    """Detect and warn about drift between root DB and tlds.txt.

    This test does NOT fail on drift — it issues warnings so the drift
    is visible in test output without blocking the pipeline. The build
    uses the root DB as its source of truth, so drift in tlds.txt is
    expected and temporary.
    """
    root_db_path = Path(SOURCE_DIR) / SOURCE_FILES["ROOT_ZONE_DB"]
    tlds_txt_path = Path(SOURCE_DIR) / SOURCE_FILES["TLD_LIST"]

    if not root_db_path.exists() or not tlds_txt_path.exists():
        pytest.skip("Source data files not available")

    drift = _compute_drift(root_db_path, tlds_txt_path)

    if drift["in_root_db_only"]:
        warnings.warn(
            f"IANA source drift: {len(drift['in_root_db_only'])} TLD(s) delegated "
            f"in root DB but not yet in tlds.txt: "
            f"{sorted(drift['in_root_db_only'])}",
            stacklevel=1,
        )

    if drift["in_tlds_txt_only"]:
        warnings.warn(
            f"IANA source drift: {len(drift['in_tlds_txt_only'])} TLD(s) in "
            f"tlds.txt but not delegated in root DB: "
            f"{sorted(drift['in_tlds_txt_only'])}",
            stacklevel=1,
        )
