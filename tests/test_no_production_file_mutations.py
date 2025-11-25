"""Test that no tests modify production data files."""

import os
from pathlib import Path

import pytest


def test_production_tlds_json_not_modified_by_tests():
    """
    Test that production tlds.json is not modified by test suite.

    This test checks the modification time of data/generated/tlds.json
    to ensure no tests are inadvertently writing to production files.
    Tests should use fixtures with monkeypatch to redirect to temp directories.
    """
    production_file = Path("data/generated/tlds.json")

    if not production_file.exists():
        pytest.skip("Production tlds.json does not exist yet")

    # Get the current mtime
    initial_mtime = os.path.getmtime(production_file)
    initial_size = production_file.stat().st_size

    # Store in module-level variable for cleanup check
    # This will be checked by the session-scoped fixture
    global _production_file_initial_state
    _production_file_initial_state = {
        "mtime": initial_mtime,
        "size": initial_size,
        "path": production_file,
    }


@pytest.fixture(scope="session", autouse=True)
def verify_production_files_unchanged():
    """Session-scoped fixture to verify production files at test session end."""
    # Setup: nothing needed
    yield

    # Teardown: check if production file was modified
    if "_production_file_initial_state" in globals():
        state = _production_file_initial_state
        production_file = state["path"]

        if not production_file.exists():
            return  # File was deleted during tests (unexpected but not our concern here)

        final_mtime = os.path.getmtime(production_file)
        final_size = production_file.stat().st_size

        if final_mtime != state["mtime"] or final_size != state["size"]:
            pytest.fail(
                f"Production file {production_file} was modified during test run! "
                f"Original mtime: {state['mtime']}, Final mtime: {final_mtime}. "
                f"Original size: {state['size']}, Final size: {final_size}. "
                f"Tests should use fixtures with monkeypatch to redirect build output to temp directories. "
                f"Example: monkeypatch.setattr('src.build.tlds.TLDS_OUTPUT_FILE', str(tmp_path / 'tlds.json'))"
            )
