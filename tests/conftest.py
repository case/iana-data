"""Shared pytest fixtures and configuration."""

import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.build.tlds import OutputPaths, build_tlds_json
from src.config import TLDS_OUTPUT_FILE
from src.utilities.download import get_iptoasn_path
from src.utilities.retry import make_request_with_retry as original_make_request


def asn_artifact_is_usable() -> bool:
    """Whether a fresh ASN build is possible.

    ASN_ARTIFACT_OPTIONAL wins over mere existence: the nightly's health gate
    already rejected the file, so rereading it would be worse than preserving.
    """
    if os.environ.get("ASN_ARTIFACT_OPTIONAL"):
        return False
    return get_iptoasn_path().exists()


def build_into(tmp: Path, *, preserve_asn: bool | None = None):
    """Build the whole typed graph into ``tmp``, honouring the fallback decision.

    preserve_asn seeds the temp tlds.json from the committed one first, so the
    preserved lookup has a baseline. Why:
    docs/plans/current/2026-09-11-asn-drift-automation.md
    """
    if preserve_asn is None:
        preserve_asn = not asn_artifact_is_usable()
    paths = OutputPaths(
        tlds_json=tmp / "tlds.json",
        tlds_index=tmp / "tlds-index.json",
        tld_dir=tmp / "tld",
        organizations_json=tmp / "organizations.json",
        places_json=tmp / "places.json",
        cultures_json=tmp / "cultures.json",
        agreements_json=tmp / "agreements.json",
    )
    if preserve_asn:
        committed = Path(TLDS_OUTPUT_FILE)
        if not committed.exists():
            reason = f"{committed} is absent, so there is no ASN to preserve"
            # Skipping here would take the structural assertions with it, green.
            if os.environ.get("CI"):
                pytest.fail(f"{reason}\n\nCI builds this before testing.")
            pytest.skip(reason)
        shutil.copyfile(committed, paths.tlds_json)
    with patch("src.utilities.metadata.METADATA_FILE", str(tmp / "metadata.json")):
        result = build_tlds_json(paths, preserve_asn=preserve_asn)
    assert not result.get("error"), result.get("error")
    return paths


@pytest.fixture(autouse=True)
def fast_retries():
    """Disable retry wait times in all tests for speed."""

    def fast_request(
        client, url, headers=None, max_attempts=3, min_wait=1, max_wait=10
    ):
        # Always use min_wait=0 in tests to skip delays
        return original_make_request(
            client,
            url,
            headers=headers,
            max_attempts=max_attempts,
            min_wait=0,
            max_wait=0,
        )

    with patch("src.utilities.download.make_request_with_retry", fast_request):
        yield


@pytest.fixture(autouse=True)
def no_sleep_delays():
    """Disable rate limiting delays in tests for speed."""
    with patch("src.utilities.download.time.sleep"):
        yield
