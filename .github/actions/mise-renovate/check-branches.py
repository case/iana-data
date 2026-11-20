"""Fail unless every branch Renovate pushed has a mise.lock that covers its mise.toml.

Renovate logs a failed `mise lock` as a warning and still pushes the branch, so read each one back.
Usage: check-branches.py <renovate-global.json> <owner/repo>, with `gh` authenticated.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

CHECK_LOCK = Path(__file__).with_name("check-lock.py")


def gh_api(*args: str) -> str:
    return subprocess.run(
        ["gh", "api", *args], capture_output=True, text=True, check=True
    ).stdout


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: check-branches.py <renovate-global.json> <owner/repo>",
            file=sys.stderr,
        )
        return 2
    policy_path, repository = Path(argv[1]), argv[2]
    failed = False
    try:
        # The policy is the one source of the prefix, so a renamed prefix cannot hide its branches.
        prefix = json.loads(policy_path.read_text(encoding="utf-8"))["branchPrefix"]
        refs = json.loads(
            gh_api(f"repos/{repository}/git/matching-refs/heads/{prefix}")
        )
        branches = [ref["ref"].removeprefix("refs/heads/") for ref in refs]
        with tempfile.TemporaryDirectory() as tmp:
            mise, lock = Path(tmp, "mise.toml"), Path(tmp, "mise.lock")
            for branch in branches:
                print(f"Checking {branch}")
                for path in (mise, lock):
                    path.write_text(
                        gh_api(
                            "-H",
                            "Accept: application/vnd.github.raw",
                            f"repos/{repository}/contents/{path.name}?ref={quote(branch, safe='')}",
                        ),
                        encoding="utf-8",
                    )
                checked = subprocess.run(
                    [sys.executable, "-I", str(CHECK_LOCK), str(mise), str(lock)],
                    check=False,
                )
                failed = failed or checked.returncode != 0
    except subprocess.CalledProcessError as err:
        print(f"::error::{' '.join(err.cmd)} failed: {err.stderr.strip()}")
        return 1
    except (OSError, ValueError, KeyError, TypeError) as err:
        print(f"::error::cannot read the Renovate branches of {repository}: {err!r}")
        return 1
    print(f"Checked {len(branches)} Renovate branch(es)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
