"""The workflows and composite actions pass jactionlint, the same check bin/lint runs."""

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def test_workflows_and_actions_pass_jactionlint():
    """Required, not skipped: a missing linter must not read as a clean run."""
    binary = shutil.which("jactionlint")
    assert binary, "jactionlint not on PATH; run `mise install`"

    result = subprocess.run(
        [binary, "--profile", "default", "--no-online", "--no-color"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
