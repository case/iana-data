"""Test that no tests modify production data files."""

import hashlib
import os
from pathlib import Path

import pytest


def _get_directory_state(directory: Path) -> dict:
    """Get state of all files in directory recursively."""
    state = {}
    if not directory.exists():
        return state

    for file_path in directory.rglob("*"):
        if file_path.is_file():
            # Store mtime, size, and hash for each file
            state[str(file_path.relative_to(directory))] = {
                "mtime": os.path.getmtime(file_path),
                "size": file_path.stat().st_size,
                "hash": hashlib.md5(file_path.read_bytes()).hexdigest(),
            }
    return state


def test_production_source_directory_not_modified_by_tests():
    """
    Test that data/source/ directory is not modified by test suite.

    This test captures the state of all files in data/source/ to ensure
    no tests are inadvertently reading from or writing to production source files.
    Tests should ONLY use fixtures in tests/fixtures/ and tmp_path, never production data.
    """
    source_dir = Path("data/source")

    if not source_dir.exists():
        pytest.skip("Production data/source directory does not exist yet")

    # Capture initial state of all files
    initial_state = _get_directory_state(source_dir)

    # Store in module-level variable for cleanup check
    global _production_source_initial_state
    _production_source_initial_state = {
        "directory": source_dir,
        "state": initial_state,
    }


def test_production_metadata_json_not_modified_by_tests():
    """
    Test that production metadata.json is not modified by test suite.

    metadata.json tracks download state and should NEVER be modified by tests.
    Tests should patch METADATA_FILE to redirect to tmp_path.
    """
    metadata_file = Path("data/generated/metadata.json")

    if not metadata_file.exists():
        pytest.skip("Production metadata.json does not exist yet")

    # Store hash of content (not just mtime, as content is what matters)
    initial_content = metadata_file.read_text()
    initial_hash = hashlib.md5(initial_content.encode()).hexdigest()

    # Store in module-level variable for cleanup check
    global _production_metadata_initial_state
    _production_metadata_initial_state = {
        "hash": initial_hash,
        "path": metadata_file,
        "content_sample": initial_content[:200],  # For debugging
    }


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

    # Teardown: check if production metadata.json was modified
    if "_production_metadata_initial_state" in globals():
        state = _production_metadata_initial_state
        metadata_file = state["path"]

        if metadata_file.exists():
            final_content = metadata_file.read_text()
            final_hash = hashlib.md5(final_content.encode()).hexdigest()

            if final_hash != state["hash"]:
                pytest.fail(
                    f"Production file {metadata_file} was MODIFIED during test run!\n"
                    f"Original hash: {state['hash']}, Final hash: {final_hash}.\n"
                    f"Tests should NEVER write to data/generated/metadata.json.\n"
                    f"Use patch('src.utilities.metadata.METADATA_FILE', str(tmp_path / 'metadata.json'))\n"
                    f"to redirect metadata operations to test directories."
                )

    # Teardown: check if production source directory was modified
    if "_production_source_initial_state" in globals():
        state = _production_source_initial_state
        source_dir = state["directory"]
        initial_state = state["state"]

        if source_dir.exists():
            final_state = _get_directory_state(source_dir)

            # Check for modified or deleted files
            for rel_path, initial_file_state in initial_state.items():
                if rel_path not in final_state:
                    pytest.fail(
                        f"Production file {source_dir / rel_path} was DELETED during test run! "
                        f"Tests should NEVER modify production data in data/source/. "
                        f"Use tmp_path and patch SOURCE_DIR to redirect to test directories."
                    )
                final_file_state = final_state[rel_path]
                if final_file_state["hash"] != initial_file_state["hash"]:
                    pytest.fail(
                        f"Production file {source_dir / rel_path} was MODIFIED during test run! "
                        f"Original hash: {initial_file_state['hash']}, Final hash: {final_file_state['hash']}. "
                        f"Tests should NEVER write to production data in data/source/. "
                        f"Use tmp_path and patch SOURCE_DIR to redirect to test directories. "
                        f"Example: patch('src.utilities.download.SOURCE_DIR', str(tmp_path / 'data' / 'source'))"
                    )

            # Check for new files
            for rel_path in final_state:
                if rel_path not in initial_state:
                    pytest.fail(
                        f"Production file {source_dir / rel_path} was CREATED during test run! "
                        f"Tests should NEVER write to production data in data/source/. "
                        f"Use tmp_path and patch SOURCE_DIR to redirect to test directories."
                    )

    # Teardown: check if production generated file was modified
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
