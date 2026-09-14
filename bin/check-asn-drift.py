#!/usr/bin/env python3
"""Report iptoasn artifact health, and ASN labels that have drifted.

Health first: bad input resolves nothing, so it reads as total drift and would
manufacture a DRIFT line for every curated label. --health-only skips the build
so the nightly can pick its build mode before building.

Exit 0 clean, 1 drift found, 2 error or unhealthy artifact. Rationale:
docs/plans/current/2026-09-11-asn-drift-automation.md
"""

import argparse
import gzip
import json
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyze.asn_health import (
    Thresholds,
    health_problems,
    is_useful_label,
    measure,
    nameserver_addresses,
    source_page_addresses,
)
from src.config import TLD_PAGES_DIR, TLDS_OUTPUT_FILE
from src.parse.iptoasn import ASNLookup, parse_gzipped_iptoasn
from src.parse.organizations import archived_names, parse_organizations_manual
from src.utilities.download import get_iptoasn_path

CLEAN, DRIFT, ERROR = 0, 1, 2

# What _resolve_asn (src/build/tlds.py) emits on a lookup miss. Distinct from
# "Not routed", which is a real iptoasn label for an unrouted prefix.
UNRESOLVED_LABEL = "Unknown"


def load_artifact(path: Path) -> tuple[ASNLookup, int]:
    """Parse the gzipped artifact into a lookup plus its usable-record count."""
    records = parse_gzipped_iptoasn(path)
    return ASNLookup(records), len(records)


def committed_addresses() -> dict[str, list[str]]:
    """Last night's nameserver addresses, from the committed graph."""
    tlds_path = Path(TLDS_OUTPUT_FILE)
    if not tlds_path.exists():
        return {}
    try:
        entries = json.loads(tlds_path.read_text(encoding="utf-8"))["tlds"]
    except (OSError, ValueError, KeyError):
        return {}
    return nameserver_addresses(entries)


def check_health(
    thresholds: Thresholds | None = None,
) -> tuple[list[str], ASNLookup | None]:
    """Problems with the current artifact, plus the lookup when it was readable.

    Returns:
        ``(problems, lookup)``. The lookup is None when the artifact could not be
        read at all, so callers must not treat it as an empty table.
    """
    path = get_iptoasn_path()
    if not path.exists():
        return [f"artifact is missing at {path}"], None
    try:
        lookup, record_count = load_artifact(path)
    except (OSError, EOFError, UnicodeDecodeError, gzip.BadGzipFile, zlib.error) as exc:
        return [f"artifact could not be read: {exc}"], None

    # Tonight's population is checked on its own: merging it with last night's
    # would let a total collection failure hide behind the committed addresses.
    tonight = source_page_addresses(Path(TLD_PAGES_DIR))
    problems = [
        f"current TLD pages: {problem}"
        for problem in health_problems(
            measure(tonight, lookup), record_count, thresholds
        )
    ]
    committed = committed_addresses()
    if committed:
        problems += [
            f"committed graph: {problem}"
            for problem in health_problems(
                measure(committed, lookup), record_count, thresholds
            )
            # The record floor is a property of the artifact, not the population.
            if "usable records" not in problem
        ]
    return problems, lookup


def repairable_damage(lookup: ASNLookup) -> int:
    """Net addresses a refresh would repair: fixed minus newly broken.

    Net, because a refresh that repairs one address while breaking another
    manufactures its own next trigger and oscillates on alternating artifacts.
    Unrepairable damage scores zero, so it cannot latch the trigger on either.
    """
    tlds_path = Path(TLDS_OUTPUT_FILE)
    if not tlds_path.exists():
        return 0
    try:
        entries = json.loads(tlds_path.read_text(encoding="utf-8"))["tlds"]
    except (OSError, ValueError, KeyError):
        return 0

    # Deduplicated: one address appears on up to 125 nameservers, so counting
    # appearances weights a popular address over a rare one and skews the net.
    committed: dict[str, str | None] = {}
    for entry in entries:
        for nameserver in entry.get("nameservers", []):
            for family in ("ipv4", "ipv6"):
                for address in nameserver.get(family, []):
                    ip = address.get("ip")
                    if ip:
                        committed.setdefault(ip, address.get("as_org"))

    repaired = 0
    broken = 0
    for ip, committed_label in committed.items():
        record = lookup.lookup(ip)
        fresh_is_useful = record is not None and is_useful_label(record.org)
        if committed_label == UNRESOLVED_LABEL:
            repaired += int(fresh_is_useful)
        elif is_useful_label(committed_label) and not fresh_is_useful:
            broken += 1
    return max(repaired - broken, 0)


def build_raw_asn_labels() -> set[str] | None:
    """Every raw as_org value on a nameserver in a freshly built graph.

    Returns None when the build reported an error, which is not "no drift".
    """
    from src.build.tlds import OutputPaths, build_tlds_json

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        paths = OutputPaths(
            tlds_json=out / "tlds.json",
            tlds_index=out / "tlds-index.json",
            tld_dir=out / "tld",
            organizations_json=out / "organizations.json",
            places_json=out / "places.json",
            cultures_json=out / "cultures.json",
            agreements_json=out / "agreements.json",
        )
        # build_tlds_json reports a write failure by return value, not by raising.
        result = build_tlds_json(paths)
        if isinstance(result, dict) and result.get("error"):
            print(f"UNHEALTHY build error: {result['error']}")
            return None
        entries = json.loads(paths.tlds_json.read_text(encoding="utf-8"))["tlds"]

    labels: set[str] = set()
    for entry in entries:
        for nameserver in entry.get("nameservers", []):
            for family in ("ipv4", "ipv6"):
                for address in nameserver.get(family, []):
                    label = address.get("as_org")
                    if label:
                        labels.add(label)
    return labels


def report_drift(raw: set[str]) -> int:
    """Print DRIFT and RETURNED lines; return the count of drifted labels."""
    drifted = 0
    for org in parse_organizations_manual():
        slug = org["slug"]
        for name in org.get("source_names", {}).get("asn", []):
            if name not in raw:
                print(f"DRIFT {slug} {name}")
                drifted += 1
        for name in archived_names(org, "asn"):
            if name in raw:
                print(f"RETURNED {slug} {name}")
    return drifted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--health-only",
        action="store_true",
        help="check the artifact and skip the build and drift report",
    )
    args = parser.parse_args()

    try:
        problems, lookup = check_health()
        damaged = 0
        if not problems and args.health_only and lookup is not None:
            damaged = repairable_damage(lookup)
    except Exception as exc:  # the advertised contract is exit 2, never a traceback
        print(f"UNHEALTHY health check failed: {exc}")
        print("asn-health: healthy=false damaged=unknown")
        return ERROR
    if problems:
        for problem in problems:
            print(f"UNHEALTHY {problem}")
        print(f"asn check: unhealthy artifact, {len(problems)} problem(s)")
        print("asn-health: healthy=false damaged=unknown")
        return ERROR
    if args.health_only:
        print("asn check: artifact healthy")
        print(f"asn check: committed graph carries {damaged} unlabelled address(es)")
        # Machine-readable line the nightly parses to pick its build mode.
        print(f"asn-health: healthy=true damaged={'true' if damaged else 'false'}")
        return CLEAN

    try:
        raw = build_raw_asn_labels()
    except Exception as exc:  # a build failure is an error exit, not "no drift"
        print(f"UNHEALTHY build failed: {exc}")
        print("asn check: build failed")
        return ERROR
    if raw is None:
        print("asn check: build reported an error")
        return ERROR

    drifted = report_drift(raw)
    print(f"asn check: {drifted} drifted label(s), artifact healthy")
    return DRIFT if drifted else CLEAN


if __name__ == "__main__":
    sys.exit(main())
