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
    # The imports are the assertion: a circular import in __init__.py raises here.
    # Each statement rebinds `src`, so only the final one is what F401 sees.
    import src
    import src.analyze
    import src.build
    import src.cli
    import src.config
    import src.parse
    import src.utilities  # noqa: F401


def test_cli_module_can_run():
    """Test that CLI can be invoked as a module (python -m src.cli).

    This is how GitHub Actions runs the CLI:
    - bin/download --iana → uv run python -m src.cli --download
    - ./bin/build --all → generate-idn-mapping + uv run python -m src.cli --build
    """
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, f"CLI failed to run: {result.stderr}"
    assert "IANA data ETL" in result.stdout
    for flag in ("--download", "--analyze", "--build"):
        assert flag in result.stdout
    assert "--download-tld-pages" not in result.stdout


def test_cli_download_flag_works():
    """--download validates its sources before fetching (used by: bin/download --iana)."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--download", "NONEXISTENT_SOURCE"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert "Invalid source(s): NONEXISTENT_SOURCE" in result.stdout + result.stderr


@pytest.mark.parametrize(
    "report", ["--data", "--idn-scripts", "--registry-agreements", "--tlds-json"]
)
def test_every_analyze_report_runs(report):
    """Each report reads the committed data, so a moved script or broken import fails here."""
    result = subprocess.run(
        ["bin/analyze", report], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not Path("bin").is_dir(), reason="bin/ directory not found")
def test_every_bin_script_is_executable():
    """Every bin/ entry point is executable; CI fails one without the bit with "Permission denied"."""
    import os

    scripts = [
        path for path in Path("bin").iterdir() if path.is_file() and not path.suffix
    ]
    assert {
        "setup",
        "lint",
        "test",
        "build",
        "download",
        "generate",
        "analyze",
        "checkly",
    } <= {path.name for path in scripts}
    for path in scripts:
        assert os.access(path, os.X_OK), f"{path} is not executable"


@pytest.mark.parametrize("script", ["analyze", "checkly", "download", "generate"])
def test_a_bin_script_rejects_extra_arguments(script):
    """A second argument would be dropped silently, so the script refuses it before running."""
    result = subprocess.run(
        [f"bin/{script}", "--help", "extra"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert f"Usage: bin/{script}" in result.stderr
