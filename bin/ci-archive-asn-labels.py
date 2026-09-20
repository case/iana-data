#!/usr/bin/env python3
"""Move drifted asn labels into ``archived.asn`` and stage the change as a patch.

Reads a drift report produced by ``bin/check-asn-drift`` and rewrites
``data/manual/organizations.json``. Dates are carried forward from the pending
branch so an unchanged proposal does not differ day to day.
Why: docs/plans/current/2026-09-11-asn-drift-automation.md
"""

import argparse
import copy
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parse.organizations import (
    archived_names,
    build_resolver,
    validate_organizations,
)
from src.utilities.content_changed import write_json_document_if_changed

OK = 0
ERROR = 2

SEED = Path("data/manual/organizations.json")


class PendingReadError(Exception):
    """The pending branch exists but its seed could not be read."""


COMPLETED = "asn check: "
HEALTHY = "artifact healthy"


def parse_drift_report(text: str) -> dict[str, set[str]]:
    """The ``DRIFT <slug> <label>`` lines, grouped by slug.

    A label may contain spaces, so the split is bounded to two fields.

    Raises:
        ValueError: on a malformed DRIFT line, or when the report carries no
            completed healthy summary. A crashed or unhealthy detector resolves
            nothing, so its empty report would otherwise read as cleared drift.
    """
    summaries = [line for line in text.splitlines() if line.startswith(COMPLETED)]
    if not any(HEALTHY in line for line in summaries):
        raise ValueError(
            f"no completed healthy detector summary; got {summaries or 'nothing'}"
        )

    drift: dict[str, set[str]] = {}
    for line in text.splitlines():
        if not line.startswith("DRIFT "):
            continue
        parts = line.split(" ", 2)
        if len(parts) != 3 or not parts[1] or not parts[2]:
            raise ValueError(f"malformed DRIFT line: {line!r}")
        drift.setdefault(parts[1], set()).add(parts[2])
    return drift


def _branch_exists(branch: str) -> bool:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"{branch}^{{commit}}"],
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
    except OSError as exc:
        raise PendingReadError(f"cannot run git: {exc}") from exc


def pending_archived_dates(branch: str) -> dict[tuple[str, str], str]:
    """``(slug, label) -> archived_on`` as the pending branch already records it.

    Raises:
        PendingReadError: when the branch exists but its seed cannot be read. Only a
            genuinely absent branch yields no dates. Treating an unreadable
            proposal as absent would restamp every label and make an unchanged
            proposal look new.
    """
    if not _branch_exists(branch):
        return {}
    try:
        blob = subprocess.run(
            ["git", "show", f"{branch}:{SEED}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError) as exc:
        raise PendingReadError(f"cannot read {SEED} on {branch}: {exc}") from exc
    try:
        orgs = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise PendingReadError(f"{branch} carries an unparseable seed: {exc}") from exc
    if not isinstance(orgs, list):
        raise PendingReadError(f"{branch} carries a seed that is not a JSON array")

    dates: dict[tuple[str, str], str] = {}
    for org in orgs:
        if not isinstance(org, dict):
            continue
        slug = org.get("slug")
        archived = org.get("archived")
        entries = archived.get("asn") if isinstance(archived, dict) else None
        if not isinstance(slug, str) or not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                when = entry.get("archived_on")
                if isinstance(when, str):
                    dates[(slug, entry["name"])] = when
    return dates


def archive_labels(
    orgs: list[dict],
    drift: dict[str, set[str]],
    carried: dict[tuple[str, str], str],
    today: str,
) -> int:
    """Move each drifted label into ``archived.asn``; return how many moved.

    An existing ``archived_on`` is never rewritten, and nothing ever leaves the
    archive. Labels already archived are skipped rather than duplicated.
    """
    moved = 0
    for org in orgs:
        slug = org.get("slug")
        if not isinstance(slug, str) or slug not in drift:
            continue
        seeded = org.get("source_names", {}).get("asn")
        if not isinstance(seeded, list):
            continue

        already = set(archived_names(org, "asn"))
        for label in sorted(drift[slug]):
            if label not in seeded:
                continue
            # A label may be seeded more than once; remove() would drop one copy
            # and leave the seed failing validation as "also a source_name".
            seeded[:] = [name for name in seeded if name != label]
            if label in already:
                moved += 1
                continue
            entries = org.setdefault("archived", {}).setdefault("asn", [])
            entries.append(
                {"name": label, "archived_on": carried.get((slug, label), today)}
            )
            entries.sort(key=lambda entry: entry["name"])
            moved += 1

        # An empty list would assert nothing yet still read as a live bucket.
        if not seeded:
            del org["source_names"]["asn"]
    return moved


def resolution_map(orgs: list[dict]) -> dict[tuple[str, str], str]:
    resolver = build_resolver(orgs)
    return {
        (source, name): org["slug"]
        for source, names in resolver.by_source.items()
        for name, org in names.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report", type=Path, help="drift report from bin/check-asn-drift"
    )
    parser.add_argument(
        "--branch",
        default="asn-drift",
        help="pending branch to carry archived_on dates forward from",
    )
    parser.add_argument(
        "--today",
        default=datetime.now(UTC).strftime("%Y-%m-%d"),
        help="the date to stamp on newly archived labels (UTC)",
    )
    args = parser.parse_args()

    try:
        drift = parse_drift_report(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"::error::cannot read drift report: {exc}")
        return ERROR
    if not drift:
        print("asn archive: no drift to archive")
        print("asn-archive: moved=0")
        return OK

    orgs = json.loads(SEED.read_text(encoding="utf-8"))
    if not isinstance(orgs, list):
        print("::error::seed is not a JSON array")
        return ERROR
    before = resolution_map(copy.deepcopy(orgs))
    try:
        carried = pending_archived_dates(args.branch)
    except PendingReadError as exc:
        print(f"::error::cannot read pending dates: {exc}")
        return ERROR
    moved = archive_labels(orgs, drift, carried, args.today)
    if not moved:
        print("asn archive: every drifted label was already archived")
        print("asn-archive: moved=0")
        return OK

    resolver = build_resolver(orgs)
    after = {
        (source, name): org["slug"]
        for source, names in resolver.by_source.items()
        for name, org in names.items()
    }
    # Defense in depth, and it runs first for the better diagnostic: any
    # resolution loss needs a malformed entry, which validate_organizations
    # rejects below, so no input reaches here that the validator would miss.
    if after != before:
        lost = sorted(set(before) - set(after))
        changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
        print(f"::error::archiving changed resolution; lost={lost} changed={changed}")
        return ERROR
    if resolver.collisions:
        print(f"::error::archiving introduced collisions: {resolver.collisions}")
        return ERROR
    problems = validate_organizations(orgs)
    if problems:
        # The nightly's own test gate runs this validator, so writing an invalid
        # seed would block the data refresh until a human edits it.
        for problem in problems:
            print(f"::error::archiving produced an invalid seed: {problem}")
        return ERROR

    if not write_json_document_if_changed(SEED, orgs):
        print("asn archive: seed already up to date")
        print("asn-archive: moved=0")
        return OK
    print(f"asn archive: archived {moved} label(s)")
    print(f"asn-archive: moved={moved}")
    return OK


if __name__ == "__main__":
    sys.exit(main())
