"""Policy for tolerating ASN label drift in the live-data integrity assertions.

iptoasn `as_org` labels are opaque third-party strings that come and go, so four
assertions here would otherwise fail whenever one stops matching and block the
nightly refresh. Rationale and the accepted losses:
docs/plans/current/2026-09-11-asn-drift-automation.md
"""

import warnings
from typing import Any

OrgRecord = dict[str, Any]
RawStrings = dict[str, dict[str, set[str]]]

# The buckets build_resolver indexes. Anything else in a seed is a curation error.
SOURCES: tuple[str, ...] = ("iana", "icann", "asn")

ASN_DRIFT = "asn_drift"
HARD = "hard"


class AsnDriftWarning(UserWarning):
    """A live-data assertion relaxed because an asn label left the raw data."""


def warn_drift(message: str) -> None:
    """Report a relaxed assertion so it is visible in pytest's warning summary."""
    warnings.warn(message, AsnDriftWarning, stacklevel=2)


def raw_org_strings(entries) -> RawStrings:
    """Map each raw per-source org string to the TLDs carrying it.

    Args:
        entries: Built tlds.json entries to scan.

    Returns:
        ``{source: {raw_value: {tld, ...}}}`` with every source present.
    """
    raw: RawStrings = {source: {} for source in SOURCES}

    def note(source: str, value: str | None, tld: str) -> None:
        if value:
            raw[source].setdefault(value, set()).add(tld)

    for entry in entries:
        tld = entry["tld"]
        orgs = entry.get("orgs", {})
        iana = orgs.get("iana", {})
        for role in ("sponsor", "admin", "tech"):
            note("iana", iana.get(role), tld)
        note("icann", orgs.get("icann", {}).get("registry_operator"), tld)
        for nameserver in entry.get("nameservers", []):
            for ip in [*nameserver.get("ipv4", []), *nameserver.get("ipv6", [])]:
                note("asn", ip.get("as_org"), tld)
    return raw


def _has_unknown_bucket(org: OrgRecord) -> bool:
    """True if source_names names a bucket the resolver does not index."""
    return bool(set(org.get("source_names", {})) - set(SOURCES))


def _resolution_keys(org: OrgRecord) -> dict[str, list[str]]:
    """Every string that resolves to ``org``, per bucket.

    Mirrors build_resolver: display_name and aliases fall back into all buckets.
    """
    source_names = org.get("source_names", {})
    fallbacks = [org["display_name"], *org.get("aliases", [])]
    return {source: [*source_names.get(source, []), *fallbacks] for source in SOURCES}


def classify_absence(org: OrgRecord, raw: RawStrings) -> str:
    """Classify an org that resolved to nothing at all.

    The test is observable, not causal: it asks whether any key still matches raw
    data, never why a key stopped matching.

    Returns:
        ``ASN_DRIFT`` when every asserted name is an unmatched asn name and
        nothing else resolves; ``HARD`` otherwise, including an org asserting no
        source names at all.
    """
    if _has_unknown_bucket(org):
        return HARD
    for source, keys in _resolution_keys(org).items():
        if any(key in raw.get(source, {}) for key in keys):
            return HARD

    buckets = {source for source, names in org.get("source_names", {}).items() if names}
    if buckets == {"asn"}:
        return ASN_DRIFT
    return HARD


def classify_missing_asn_role(org: OrgRecord, raw: RawStrings) -> str:
    """Classify an org missing an asn relationship, looking only at the asn bucket.

    Scoped deliberately: an org holding a live iana key can still lose its asn
    role, and the all-bucket test in classify_absence would never reach ASN_DRIFT
    for it. Carries no precondition about other roles.
    """
    if _has_unknown_bucket(org):
        return HARD
    if any(key in raw.get("asn", {}) for key in _resolution_keys(org)["asn"]):
        return HARD
    if not org.get("source_names", {}).get("asn"):
        return HARD
    return ASN_DRIFT


def split_unmatched_source_names(
    orgs, raw: RawStrings
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Split unmatched source_names into hard failures and asn-drift warnings.

    Returns:
        ``(hard, drift)`` lists of ``(slug, source, name)``.
    """
    hard: list[tuple[str, str, str]] = []
    drift: list[tuple[str, str, str]] = []
    for org in orgs:
        for source, names in org.get("source_names", {}).items():
            for name in names:
                if name in raw.get(source, {}):
                    continue
                bucket = drift if source == "asn" else hard
                bucket.append((org["slug"], source, name))
    return hard, drift


def split_orphans(orgs, raw: RawStrings) -> tuple[list[str], list[str]]:
    """Split roleless orgs into hard failures and asn-drift warnings."""
    hard: list[str] = []
    drift: list[str] = []
    for org in orgs:
        if org.get("roles"):
            continue
        target = drift if classify_absence(org, raw) == ASN_DRIFT else hard
        target.append(org["slug"])
    return hard, drift


def split_missing_slugs(
    missing, by_slug, raw: RawStrings
) -> tuple[list[str], list[str]]:
    """Split slugs absent from an expected asn relationship.

    A slug with no seed record is a hard failure: there is no evidence to weigh.
    """
    hard: list[str] = []
    drift: list[str] = []
    for slug in missing:
        org = by_slug.get(slug)
        if org is not None and classify_missing_asn_role(org, raw) == ASN_DRIFT:
            drift.append(slug)
        else:
            hard.append(slug)
    return hard, drift
