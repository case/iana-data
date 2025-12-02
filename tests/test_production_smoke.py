"""Smoke tests that validate production CLI and workflow commands work.

These tests ensure that the actual commands used in GitHub Actions workflows
will succeed. They catch issues that unit tests miss, such as:
- Circular imports (only manifest when importing packages, not individual modules)
- CLI entry point failures
- Module initialization issues
- Integration between components

These tests run the actual commands that production uses, not just the
underlying functions.
"""

import subprocess
import sys
from pathlib import Path

import pytest


def test_module_can_be_imported():
    """Test that src package can be imported (catches circular imports).

    This is critical because:
    - Unit tests import specific modules: `from src.parse.rdap_json import ...`
    - Production imports the package: `python -m src.cli`

    Circular imports only manifest during package-level imports.
    """
    # This will fail if there's a circular import in __init__.py files
    import src  # noqa: F401
    import src.parse  # noqa: F401
    import src.utilities  # noqa: F401
    import src.analyze  # noqa: F401
    import src.build  # noqa: F401


def test_cli_module_can_run():
    """Test that CLI can be invoked as a module (python -m src.cli).

    This is how GitHub Actions runs the CLI:
    - make download-core → uv run python -m src.cli --download
    - make download-tld-pages → uv run python -m src.cli --download-tld-pages
    - make build → uv run python -m src.cli --build
    """
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, f"CLI failed to run: {result.stderr}"
    assert "IANA data ETL" in result.stdout
    assert "--download" in result.stdout
    assert "--build" in result.stdout
    assert "--download-tld-pages" in result.stdout


def test_cli_download_flag_works():
    """Test that --download flag works (used by: make download-core)."""
    # Don't actually download, just verify CLI accepts the flag
    # The actual download is mocked in unit tests
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--download", "NONEXISTENT_SOURCE"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Should fail gracefully with error about unknown source, not crash
    # Exit code doesn't matter - we just care it doesn't have import errors
    assert "circular import" not in result.stderr.lower()
    assert "ImportError" not in result.stderr


def test_cli_download_tld_pages_flag_works():
    """Test that --download-tld-pages flag works (used by: make download-tld-pages GROUPS='a b')."""
    # Pass a specific invalid TLD to avoid actually downloading anything
    # We just want to verify the CLI accepts the flag and doesn't have import errors
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--download-tld-pages", "nonexistent-tld-for-testing"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Should not crash with import errors
    assert "circular import" not in result.stderr.lower()
    assert "ImportError" not in result.stderr
    # Either succeeds or fails gracefully (exit code doesn't matter for this test)


def test_cli_analyze_flag_works():
    """Test that --analyze flag works (used by: make analyze)."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--analyze"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Should not crash with import errors
    assert "circular import" not in result.stderr.lower()
    assert "ImportError" not in result.stderr


@pytest.mark.skipif(
    not Path("Makefile").exists(),
    reason="Makefile not found"
)
def test_makefile_targets_exist():
    """Verify that all Makefile targets used in GitHub Actions exist.

    GitHub Actions workflow uses these Make targets:
    - make download-core
    - make download-tld-pages GROUPS="..."
    - make generate-idn-mapping
    - make test
    - make build
    """
    makefile_content = Path("Makefile").read_text()

    required_targets = [
        "download-core",
        "download-tld-pages",
        "generate-idn-mapping",
        "test",
        "build",
    ]

    for target in required_targets:
        assert f".PHONY: {target}" in makefile_content or f"{target}:" in makefile_content, \
            f"Required Make target '{target}' not found in Makefile (used by GitHub Actions)"


def test_all_cli_subcommands_have_help():
    """Ensure all CLI subcommands are documented and accessible."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0

    # All subcommands used in production should be documented
    required_flags = [
        "--download",
        "--download-tld-pages",
        "--analyze",
        "--build",
    ]

    for flag in required_flags:
        assert flag in result.stdout, \
            f"Required CLI flag '{flag}' not found in --help output (used by Makefile/GitHub Actions)"


def test_package_has_no_syntax_errors():
    """Verify all Python files in src/ can be compiled.

    This catches syntax errors that might not be covered by tests.
    """
    src_dir = Path("src")
    python_files = list(src_dir.rglob("*.py"))

    assert len(python_files) > 0, "No Python files found in src/"

    for py_file in python_files:
        try:
            compile(py_file.read_text(), str(py_file), "exec")
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {py_file}: {e}")


def test_no_circular_imports_in_package_structure():
    """Test importing all packages doesn't cause circular import.

    This validates the entire package structure, not just individual modules.
    """
    packages = [
        "src",
        "src.analyze",
        "src.build",
        "src.cli",
        "src.config",
        "src.parse",
        "src.utilities",
    ]

    for package_name in packages:
        try:
            __import__(package_name)
        except ImportError as e:
            if "circular import" in str(e).lower():
                pytest.fail(f"Circular import detected in {package_name}: {e}")
            # Other ImportErrors might be OK (missing optional deps, etc.)


def test_cli_entry_points_are_defined():
    """Verify that the CLI module structure is correct."""
    # The CLI should be runnable as: python -m src.cli
    cli_module = Path("src/cli.py")
    assert cli_module.exists(), "src/cli.py not found"

    # Should have __main__ guard or be executable
    cli_content = cli_module.read_text()
    assert 'if __name__ == "__main__"' in cli_content or "def main(" in cli_content, \
        "CLI module should have main entry point"
