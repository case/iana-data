"""Health signals for the iptoasn artifact, used to pick a build mode.

An unhealthy artifact downgrades the nightly to --preserve-asn rather than
blocking it, so these are tripwires for catastrophic loss, not calibrated
limits. Thresholds, their measured baseline, and the attacks each one answers:
docs/plans/current/2026-09-11-asn-drift-automation.md
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from ..parse.iana_tlds_json import IanaTld
from ..parse.iptoasn import ASNLookup

# as_org values that carry no operator identity. Excluded from useful-label
# counts, or a total collapse to one placeholder reads as healthy diversity.
SENTINEL_LABELS: frozenset[str] = frozenset({"Unknown", "Not routed"})

FAMILIES: tuple[str, ...] = ("ipv4", "ipv6")


def is_useful_label(org: str | None) -> bool:
    """True when a label identifies an operator, after stripping whitespace.

    Empty and whitespace-only labels are as useless as a sentinel; treating them
    as useful lets an artifact of blank org fields pass the coverage floor.
    """
    if not org:
        return False
    return org.strip() not in SENTINEL_LABELS and bool(org.strip())


@dataclass(frozen=True)
class Thresholds:
    """Inclusive failure boundaries. Defaults are the plan's measured values."""

    max_unrouted_ipv4: int = 25
    max_unrouted_ipv6: int = 60
    min_useful_label_coverage: float = 0.95
    min_addresses_ipv4: int = 4000
    min_addresses_ipv6: int = 3800
    min_records: int = 500_000
    # 40h, not 48h: the safe band is 37.2-40.7h against 80 nights of observed
    # queue delay. Why: docs/memory/log/2026-09-24-iptoasn-freshness.md
    max_age_hours: float = 40.0
    max_clock_skew_minutes: float = 5.0

    def max_unrouted(self, family: str) -> int:
        return self.max_unrouted_ipv4 if family == "ipv4" else self.max_unrouted_ipv6

    def min_addresses(self, family: str) -> int:
        return self.min_addresses_ipv4 if family == "ipv4" else self.min_addresses_ipv6


@dataclass(frozen=True)
class FamilyHealth:
    """One address family's resolution against an artifact."""

    family: str
    total: int
    unrouted: int
    useful_labelled: int

    @property
    def useful_label_coverage(self) -> float:
        """Fraction of addresses carrying a non-sentinel label; 0.0 when empty.

        Never 1.0 for an empty family: 0/0 must not read as perfect coverage.
        """
        if self.total == 0:
            return 0.0
        return self.useful_labelled / self.total


def measure(
    addresses: Mapping[str, Iterable[str]], lookup: ASNLookup
) -> dict[str, FamilyHealth]:
    """Resolve each family's addresses against ``lookup``.

    Args:
        addresses: ``{family: addresses}``. Deduplicated here, so callers may
            pass repeats.
        lookup: The ASN lookup built from the artifact under test.

    Returns:
        One FamilyHealth per family in FAMILIES, present even when empty.
    """
    out: dict[str, FamilyHealth] = {}
    for family in FAMILIES:
        unique = {ip for ip in addresses.get(family, ()) if ip}
        unrouted = 0
        useful = 0
        for ip in unique:
            record = lookup.lookup(ip)
            if record is None or record.asn == 0:
                unrouted += 1
            if record is not None and is_useful_label(record.org):
                useful += 1
        out[family] = FamilyHealth(
            family=family,
            total=len(unique),
            unrouted=unrouted,
            useful_labelled=useful,
        )
    return out


def health_problems(
    families: Mapping[str, FamilyHealth],
    record_count: int,
    thresholds: Thresholds | None = None,
) -> list[str]:
    """Report why the artifact is unhealthy, or an empty list.

    Returns:
        One human-readable string per failed signal. An empty list means every
        signal passed; a missing family is itself a problem, never a pass.
    """
    limits = thresholds or Thresholds()
    problems: list[str] = []

    if record_count < limits.min_records:
        problems.append(
            f"artifact has {record_count} usable records, "
            f"below the {limits.min_records} floor"
        )

    for family in FAMILIES:
        health = families.get(family)
        if health is None:
            problems.append(f"{family}: not measured")
            continue
        if health.total == 0:
            problems.append(f"{family}: no addresses to resolve")
            continue
        if health.total < limits.min_addresses(family):
            problems.append(
                f"{family}: {health.total} addresses, "
                f"below the {limits.min_addresses(family)} floor"
            )
        if health.unrouted > limits.max_unrouted(family):
            problems.append(
                f"{family}: {health.unrouted} unrouted addresses, "
                f"above the {limits.max_unrouted(family)} ceiling"
            )
        coverage = health.useful_label_coverage
        if coverage < limits.min_useful_label_coverage:
            problems.append(
                f"{family}: {coverage:.4%} of addresses carry a useful label, "
                f"below the {limits.min_useful_label_coverage:.0%} floor"
            )
    return problems


def _parse_artifact_stamp(created_at: str) -> datetime | str:
    """The parsed timestamp, or the reason it is unusable."""
    if not created_at or not created_at.strip():
        return "artifact creation timestamp is empty"
    try:
        stamp = datetime.fromisoformat(created_at.strip())
    except ValueError:
        return f"artifact creation timestamp is unparseable: {created_at!r}"
    if stamp.tzinfo is None:
        return f"artifact creation timestamp has no timezone: {created_at!r}"
    return stamp


def artifact_age_hours(created_at: str, now: datetime) -> float | None:
    """The artifact's age in hours, or None when the timestamp is unusable.

    Negative when the timestamp is ahead of ``now``. Logged on every run so the
    threshold can be refined from observation rather than argument.
    """
    stamp = _parse_artifact_stamp(created_at)
    if isinstance(stamp, str):
        return None
    return (now - stamp).total_seconds() / 3600


def artifact_age_problem(
    created_at: str,
    now: datetime,
    thresholds: Thresholds | None = None,
) -> str | None:
    """Why the artifact is too old to trust, or None when its age is acceptable.

    Args:
        created_at: RFC3339 timestamp from the producer run. An empty string is a
            problem, never a pass: only an omitted value skips the check, and that
            decision belongs to the caller.
        now: Evaluated against this, so a test can pin the exact boundary.
        thresholds: Supplies max_age_hours and max_clock_skew_minutes.

    Returns:
        One human-readable string, or None. A timezone-naive or unparseable
        timestamp is a problem, as is one dated past the clock-skew tolerance.
    """
    limits = thresholds or Thresholds()
    stamp = _parse_artifact_stamp(created_at)
    if isinstance(stamp, str):
        return stamp

    age_hours = (now - stamp).total_seconds() / 3600
    if age_hours < -(limits.max_clock_skew_minutes / 60):
        return (
            f"artifact creation timestamp is {-age_hours:.2f}h in the future, "
            f"beyond the {limits.max_clock_skew_minutes:.0f}m clock-skew tolerance"
        )
    if age_hours > limits.max_age_hours:
        return (
            f"artifact is {age_hours:.2f}h old, "
            f"above the {limits.max_age_hours:.0f}h ceiling"
        )
    return None


def nameserver_addresses(entries: Iterable[dict]) -> dict[str, list[str]]:
    """Collect every nameserver address in built TLD entries, per family."""
    out: dict[str, list[str]] = {family: [] for family in FAMILIES}
    for entry in entries:
        for nameserver in entry.get("nameservers", []):
            for family in FAMILIES:
                for address in nameserver.get(family, []):
                    ip = address.get("ip")
                    if ip:
                        out[family].append(ip)
    return out


def source_nameserver_addresses(records: Iterable[IanaTld]) -> dict[str, list[str]]:
    """Tonight's nameserver addresses, from the downloaded IANA TLD JSON records.

    The committed graph holds last night's population, so an artifact can cover
    it perfectly and still omit ranges holding an address introduced today.
    """
    out: dict[str, list[str]] = {family: [] for family in FAMILIES}
    for record in records:
        for nameserver in record.nameservers:
            out["ipv4"].extend(nameserver.ipv4)
            out["ipv6"].extend(nameserver.ipv6)
    return out


def merge_addresses(*sets: Mapping[str, Iterable[str]]) -> dict[str, list[str]]:
    """Union several per-family address sets, preserving family keys."""
    out: dict[str, list[str]] = {family: [] for family in FAMILIES}
    for source in sets:
        for family in FAMILIES:
            out[family].extend(source.get(family, ()))
    return out
