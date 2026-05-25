"""Build data/generated/organizations.json.

Transposes the built TLD list into a per-org roles reverse-index (via the same
OrgResolver the tlds.json annotations use) and writes the seed + roles by slug.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from ..parse.organizations import OrgRecord, OrgResolver
from ..utilities.content_changed import write_json_if_changed

logger = logging.getLogger(__name__)

_DESCRIPTION = (
    "Organizations that play roles for TLDs in the IANA root zone, with a "
    "reverse-index of those roles. Consolidated subset: this covers the curated "
    "multi-source organizations only; the single-source long tail is not yet "
    "included, so absence here does not mean a TLD has no operator."
)

_SOURCES = [
    "data/source/iana-root.html (IANA)",
    "data/source/icann-gtlds.json (ICANN)",
    "data/source/iptoasn/ip2asn-combined.tsv.gz (ASN routing data)",
    "data/manual/organizations.json (editorial)",
]

# Canonical source/role key order so roles reads uniformly and diffs cleanly.
_ROLE_ORDER: dict[str, tuple[str, ...]] = {
    "iana": ("sponsor", "admin", "tech"),
    "icann": ("registry_operator",),
    "asn": ("operator",),
}


def build_organizations_json(
    tlds: list[dict],
    manual_orgs: list[OrgRecord],
    resolver: OrgResolver,
    output_path: Path,
) -> tuple[bool, str]:
    """Transpose roles onto the org seed and write organizations.json.

    Args:
        tlds: The built TLD entries (the source of role relationships).
        manual_orgs: The editorial org seed (the identity layer).
        resolver: Shared resolver mapping raw per-source strings to orgs.
        output_path: Destination for the generated artifact.

    Returns:
        The ``(changed, status)`` tuple from ``write_json_if_changed``.
    """
    roles = _transpose_roles(tlds, resolver)

    out_orgs: list[dict] = []
    for org in sorted(manual_orgs, key=lambda o: o["slug"]):
        record = dict(org)
        org_roles = roles.get(org["slug"])
        if org_roles:
            record["roles"] = org_roles
        out_orgs.append(record)

    output = {
        "description": _DESCRIPTION,
        "publication": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": _SOURCES,
        "orgs": out_orgs,
    }

    changed, status = write_json_if_changed(
        output_path, output, exclude_fields=["publication"], indent=2
    )
    logger.info("organizations.json: %s (changed=%s)", status, changed)
    return changed, status


def _transpose_roles(
    tlds: list[dict], resolver: OrgResolver
) -> dict[str, dict[str, dict[str, list[str]]]]:
    """Build ``{slug: {source: {role: [tlds]}}}`` from the built TLD entries.

    TLD lists are deduped and sorted; empty buckets and roles never appear
    because an entry is created only when a real org/TLD pair resolves.
    """
    acc: dict[str, dict[str, dict[str, set[str]]]] = {}

    def add(org: OrgRecord | None, source: str, role: str, tld: str) -> None:
        if org is None:
            return
        acc.setdefault(org["slug"], {}).setdefault(source, {}).setdefault(
            role, set()
        ).add(tld)

    # Re-resolve raw org strings here (not the tlds.json annotation slugs) so
    # this artifact stays independent of the annotation schema.
    for entry in tlds:
        tld = entry["tld"]
        orgs = entry.get("orgs", {})

        iana = orgs.get("iana", {})
        for role in ("sponsor", "admin", "tech"):
            add(resolver.resolve("iana", iana.get(role)), "iana", role, tld)

        registry_operator = orgs.get("icann", {}).get("registry_operator")
        add(
            resolver.resolve("icann", registry_operator),
            "icann",
            "registry_operator",
            tld,
        )

        for as_org in _nameserver_as_orgs(entry):
            add(resolver.resolve("asn", as_org), "asn", "operator", tld)

    result: dict[str, dict[str, dict[str, list[str]]]] = {}
    for slug, by_source in acc.items():
        ordered: dict[str, dict[str, list[str]]] = {}
        for source, roles in _ROLE_ORDER.items():
            present = {
                role: sorted(by_source[source][role])
                for role in roles
                if role in by_source.get(source, {})
            }
            if present:
                ordered[source] = present
        result[slug] = ordered
    return result


def _nameserver_as_orgs(entry: dict) -> set[str]:
    """Unique non-empty AS-org names across a TLD's nameserver IPs."""
    found: set[str] = set()
    for ns in entry.get("nameservers", []):
        for ip in [*ns.get("ipv4", []), *ns.get("ipv6", [])]:
            as_org = ip.get("as_org")
            if as_org:
                found.add(as_org)
    return found
