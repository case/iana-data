"""Static analysis to detect circular imports using pydeps.

This test uses the pydeps tool to analyze import dependencies and detect cycles.
pydeps is specifically designed for this purpose and is actively maintained.

Benefits over manual analysis:
- Comprehensive dependency graph analysis
- Actively maintained tool
- Industry standard for Python circular import detection
- Can generate visual dependency graphs for debugging

See: https://github.com/thebjorn/pydeps
"""

import subprocess
import sys


def test_no_circular_imports_with_pydeps():
    """Use pydeps to statically detect circular imports in src/ package.

    This test analyzes the entire import dependency graph and fails if any
    circular dependencies are found. This catches the type of bug we just
    fixed (circular import in src.utilities.download) before it reaches production.

    pydeps analyzes import statements without executing code, so it's:
    - Fast (no import execution)
    - Comprehensive (checks entire codebase)
    - Deterministic (same result every time)

    This would have immediately caught the circular import bug:
        src.utilities → src.parse → src.utilities (circular!)
    """
    result = subprocess.run(
        [sys.executable, "-m", "pydeps", "src", "--no-output"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # pydeps outputs cycle information to stdout/stderr
    output = result.stdout + result.stderr

    # Check if cycles were detected
    # pydeps will output cycle information and exit with non-zero if cycles found
    if result.returncode != 0 or "Cycle" in output or "circular" in output.lower():
        error_msg = [
            "Circular import dependencies detected by pydeps!",
            "",
            "Output:",
            output,
            "",
            "Circular imports cause:",
            "  - ImportError when running as module (python -m src.cli)",
            "  - Initialization order issues in production",
            "  - Hard-to-debug runtime failures",
            "",
            "Fix by:",
            "  1. Use lazy imports (import inside functions)",
            "  2. Restructure code to break dependency cycle",
            "  3. Create new module for shared dependencies",
            "",
            "To visualize the dependency graph:",
            "  uv run pydeps src",
        ]
        assert False, "\n".join(error_msg)


def test_pydeps_is_installed():
    """Verify pydeps is available for import analysis."""
    result = subprocess.run(
        [sys.executable, "-m", "pydeps", "--version"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        "pydeps not installed. Run: uv add --dev pydeps==3.0.1"
    )
    assert "3.0.1" in result.stdout or "3.0.1" in result.stderr, (
        f"Expected pydeps 3.0.1, got: {result.stdout}"
    )
