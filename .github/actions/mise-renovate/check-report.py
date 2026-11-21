"""Fail unless Renovate's JSON report shows it read and checked every tool in mise.toml.

Renovate exits 0 for a disabled repository (no package files, forbidden, not found), for a tool
whose lookup failed, for a tool it never extracted, and for a failed lock update. Each looks like a
run with nothing to update. Its report, set against the checked-out mise.toml, tells them apart.
"""

import json
import sys
import tomllib
from pathlib import Path

MANAGER = "mise"
PACKAGE_FILE = "mise.toml"
LOCK_FILE = "mise.lock"
TOOLS_DEP_TYPE = "tools"


def problems(report: dict, repository: str, declared_tools: int) -> list[str]:
    """Return why the report does not prove mise.toml was processed; empty means it does."""
    repo = report.get("repositories", {}).get(repository)
    if repo is None:
        return [f"the report has no entry for {repository}"]
    found: list[str] = []
    # Renovate logs a failed `mise lock` as a warning and still exits 0, so any recorded problem fails.
    for problem in (report.get("problems") or []) + (repo.get("problems") or []):
        found.append(f"Renovate reported a problem: {problem.get('msg', problem)}")
    if repo.get("status") == "disabled":
        found.append(f"Renovate disabled {repository}")
    files = repo.get("packageFiles", {}).get(MANAGER, [])
    matching = [entry for entry in files if entry.get("packageFile") == PACKAGE_FILE]
    if not matching:
        found.append(f"the {MANAGER} manager did not extract {PACKAGE_FILE}")
    elif not all(LOCK_FILE in (entry.get("lockFiles") or []) for entry in matching):
        found.append(f"Renovate did not associate {LOCK_FILE} with {PACKAGE_FILE}")
    deps = [dep for entry in matching for dep in entry.get("deps") or []]
    # Counted, not named: Renovate can rename a tool, but it cannot drop one unnoticed.
    extracted = sum(1 for dep in deps if dep.get("depType") == TOOLS_DEP_TYPE)
    if matching and extracted != declared_tools:
        found.append(
            f"{PACKAGE_FILE} declares {declared_tools} tools but Renovate extracted {extracted}"
        )
    # A failed lookup leaves the tool with no updates and the run green, like a current tool.
    for dep in deps:
        name = dep.get("depName", "<unnamed>")
        if dep.get("skipReason"):
            found.append(f"{name} was skipped: {dep['skipReason']}")
        if dep.get("lookupFailed"):
            found.append(f"{name} lookup failed")
        for warning in dep.get("warnings") or []:
            found.append(
                f"{name}: {warning.get('topic', 'warning')}: {warning.get('message', '')}"
            )
    return found


def main(argv: list[str]) -> int:
    if not (len(argv) == 4 or argv[2:] == ["--clear"]):
        print(
            "usage: check-report.py <renovate-global.json> (<owner/repo> <mise.toml> | --clear)",
            file=sys.stderr,
        )
        return 2
    policy_path = Path(argv[1])
    try:
        report_path = Path(
            json.loads(policy_path.read_text(encoding="utf-8"))["reportPath"]
        )
    except (OSError, ValueError, KeyError) as err:
        print(f"::error::{policy_path} names no readable reportPath: {err!r}")
        return 1
    if argv[2] == "--clear":
        # Before Renovate runs, so a report left by an earlier job cannot pass the check.
        try:
            report_path.unlink(missing_ok=True)
        except OSError as err:
            print(f"::error::cannot clear the earlier report at {report_path}: {err}")
            return 1
        return 0
    repository, mise_path = argv[2], Path(argv[3])
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"::error::Renovate report unreadable at {report_path}: {err}")
        return 1
    try:
        tools = tomllib.loads(mise_path.read_text(encoding="utf-8")).get("tools", {})
    except (OSError, ValueError) as err:
        print(
            f"::error::{mise_path} unreadable; check out the repository before this action: {err}"
        )
        return 1
    if not tools:
        print(f"::error::{mise_path} declares no [tools]")
        return 1
    found = problems(report, repository, len(tools))
    for problem in found:
        print(f"::error::{problem}")
    if found:
        return 1
    print(f"Renovate checked all {len(tools)} tools in {PACKAGE_FILE} for {repository}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
