"""Referential-integrity tests for organizations.json and its tlds.json FKs.

This dataset is a relational database in disguise: tlds.json annotations carry
slug foreign keys into organizations.json, and organizations.json roles are the
reverse index of the same relationships. These tests are the integrity
constraints SQL would give us for free. A failure means the curated data
(data/manual/organizations.json) and the generated artifacts disagree, and the
fix is in the data, not the test.
"""

import difflib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.build.tlds import OutputPaths, build_tlds_json
from src.parse.organizations import build_resolver, parse_organizations_manual

# Annotation prefix -> (source bucket, role) for the scalar registry positions.
SCALAR_ROLES = [
    ("iana_sponsor", "iana", "sponsor"),
    ("iana_admin", "iana", "admin"),
    ("iana_tech", "iana", "tech"),
    ("icann_registry_operator", "icann", "registry_operator"),
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One fresh build, yielding the parsed tlds.json and organizations.json.

    The committed data/generated/organizations.json does not exist until a
    `./bin/build`, so these tests build into a temp dir rather than reading the
    repo's generated files.
    """
    tmp = tmp_path_factory.mktemp("orgs_integrity")
    with patch("src.utilities.metadata.METADATA_FILE", str(tmp / "metadata.json")):
        paths = OutputPaths(
            tlds_json=tmp / "tlds.json",
            tlds_index=tmp / "tlds-index.json",
            tld_dir=tmp / "tld",
            organizations_json=tmp / "organizations.json",
            places_json=tmp / "places.json",
            cultures_json=tmp / "cultures.json",
            agreements_json=tmp / "agreements.json",
        )
        build_tlds_json(paths)

    tlds = {e["tld"]: e for e in json.loads(paths.tlds_json.read_text())["tlds"]}
    orgs_doc = json.loads(paths.organizations_json.read_text())
    by_slug = {o["slug"]: o for o in orgs_doc["orgs"]}
    return SimpleNamespace(
        tlds=tlds, orgs=orgs_doc["orgs"], doc=orgs_doc, by_slug=by_slug
    )


def _annotation_slugs(annotations: dict) -> list[str]:
    """All org slug FKs an annotations block carries (scalar + as_org list)."""
    slugs = [
        annotations[f"{prefix}_slug"]
        for prefix, _, _ in SCALAR_ROLES
        if f"{prefix}_slug" in annotations
    ]
    slugs.extend(annotations.get("as_org_slugs", []))
    return slugs


def test_resolver_has_no_collisions():
    """No source_name string is claimed by two different orgs in one bucket."""
    resolver = build_resolver(parse_organizations_manual())

    assert resolver.collisions == [], (
        f"ambiguous source_names in organizations.json: {resolver.collisions}"
    )


def test_every_org_has_at_least_one_role(built):
    """Every curated org resolves to a real role (no orphan identity records)."""
    orphans = [o["slug"] for o in built.orgs if not o.get("roles")]

    assert orphans == [], (
        f"orgs in organizations.json that map to zero TLDs: {orphans}. "
        "Either the org's source_names don't match live data, or it should be removed."
    )


def test_annotation_slugs_are_valid_foreign_keys(built):
    """Every *_slug in tlds.json points to a real org in organizations.json."""
    dangling = []
    for tld, entry in built.tlds.items():
        for slug in _annotation_slugs(entry.get("annotations", {})):
            if slug not in built.by_slug:
                dangling.append((tld, slug))

    assert dangling == [], (
        f"annotation slugs with no organizations.json record: {dangling[:10]}"
    )


def test_annotation_alias_matches_org_display_name(built):
    """Each *_alias equals the display_name of the org its *_slug points to."""
    mismatches = []
    for tld, entry in built.tlds.items():
        annotations = entry.get("annotations", {})
        for prefix, _, _ in SCALAR_ROLES:
            slug = annotations.get(f"{prefix}_slug")
            alias = annotations.get(f"{prefix}_alias")
            if slug and built.by_slug[slug]["display_name"] != alias:
                mismatches.append((tld, prefix, alias, slug))
        aliases = annotations.get("as_org_aliases", [])
        slugs = annotations.get("as_org_slugs", [])
        if len(aliases) != len(slugs):
            mismatches.append((tld, "as_org_length", len(aliases), len(slugs)))
        else:
            for alias, slug in zip(aliases, slugs):
                if built.by_slug[slug]["display_name"] != alias:
                    mismatches.append((tld, "as_org_parity", alias, slug))

    assert mismatches == [], f"alias/slug display_name mismatches: {mismatches[:10]}"


def test_roles_round_trip_with_scalar_annotations(built):
    """A scalar role membership in organizations.json matches the TLD's slug FK,
    in both directions."""
    for prefix, source, role in SCALAR_ROLES:
        # Forward: annotation slug => TLD is in that org's role list.
        for tld, entry in built.tlds.items():
            slug = entry.get("annotations", {}).get(f"{prefix}_slug")
            if slug:
                role_tlds = (
                    built.by_slug[slug].get("roles", {}).get(source, {}).get(role, [])
                )
                assert tld in role_tlds, (
                    f"{tld}.{prefix}_slug={slug} but {tld} missing from "
                    f"{slug}.roles.{source}.{role}"
                )
        # Backward: org role list => each TLD's annotation points back.
        for org in built.orgs:
            for tld in org.get("roles", {}).get(source, {}).get(role, []):
                assert (
                    built.tlds[tld]["annotations"].get(f"{prefix}_slug") == org["slug"]
                ), (
                    f"{org['slug']}.roles.{source}.{role} lists {tld} but "
                    f"{tld}.{prefix}_slug != {org['slug']}"
                )


def test_roles_round_trip_with_asn_annotations(built):
    """asn.operator membership matches the TLD's as_org_slugs, both directions."""
    for tld, entry in built.tlds.items():
        for slug in entry.get("annotations", {}).get("as_org_slugs", []):
            operator_tlds = (
                built.by_slug[slug].get("roles", {}).get("asn", {}).get("operator", [])
            )
            assert tld in operator_tlds, (
                f"{tld} carries as_org_slug {slug} but is not in its asn.operator"
            )
    for org in built.orgs:
        for tld in org.get("roles", {}).get("asn", {}).get("operator", []):
            assert org["slug"] in built.tlds[tld]["annotations"].get(
                "as_org_slugs", []
            ), (
                f"{org['slug']}.roles.asn.operator lists {tld} but {tld} lacks the slug FK"
            )


def test_role_tlds_are_ascii_keys_in_tlds_json(built):
    """Every TLD in roles is an A-label (ASCII) and a real tlds.json key. Encodes
    the identifier standard: A-labels are the join key, U-labels are display-only."""
    bad = []
    for org in built.orgs:
        for source, roles in org.get("roles", {}).items():
            for role, tld_list in roles.items():
                for tld in tld_list:
                    if not tld.isascii():
                        bad.append((org["slug"], source, role, tld, "non-ascii"))
                    elif tld not in built.tlds:
                        bad.append((org["slug"], source, role, tld, "unknown-tld"))

    assert bad == [], f"role TLDs that are non-ASCII or not a tlds.json key: {bad[:10]}"


def _diagnose_unmatched(unmatched, raw_tlds):
    """Render unmatched source_names with the nearest still-existing raw values
    and the TLDs they appear on, to show whether each is a near-dup or fully stale."""
    lines = []
    for slug, source, name in unmatched:
        candidates = sorted(raw_tlds.get(source, {}))
        near = difflib.get_close_matches(name, candidates, n=3, cutoff=0.6)
        lines.append(f"  {slug} / {source} / {name!r} — no raw match")
        if not near:
            lines.append("      (no near matches — likely fully stale)")
        for cand in near:
            tlds = sorted(raw_tlds[source].get(cand, ()))
            shown = ", ".join(tlds[:8]) + ("…" if len(tlds) > 8 else "")
            lines.append(f"      nearest existing: {cand!r}  (on: {shown})")
    return (
        "source_names strings not found in any tlds.json raw value for that "
        "source (fix the seed or move to aliases):\n" + "\n".join(lines)
    )


def test_source_names_appear_in_raw_data(built):
    """Every source_names string must occur as a raw value in tlds.json for that
    source. A string that matches nothing is a stale/typo'd curation entry that
    belongs in aliases, not source_names."""
    raw_tlds: dict[str, dict[str, set[str]]] = {"iana": {}, "icann": {}, "asn": {}}

    def note(source: str, value: str | None, tld: str) -> None:
        if value:
            raw_tlds[source].setdefault(value, set()).add(tld)

    for entry in built.tlds.values():
        tld = entry["tld"]
        orgs = entry.get("orgs", {})
        iana = orgs.get("iana", {})
        for role in ("sponsor", "admin", "tech"):
            note("iana", iana.get(role), tld)
        note("icann", orgs.get("icann", {}).get("registry_operator"), tld)
        for ns in entry.get("nameservers", []):
            for ip in [*ns.get("ipv4", []), *ns.get("ipv6", [])]:
                note("asn", ip.get("as_org"), tld)

    unmatched = []
    for org in built.orgs:
        for source, names in org.get("source_names", {}).items():
            for name in names:
                if name not in raw_tlds.get(source, {}):
                    unmatched.append((org["slug"], source, name))

    assert unmatched == [], _diagnose_unmatched(unmatched, raw_tlds)


def test_organizations_sorted_by_slug_with_envelope(built):
    """orgs are sorted by slug and the envelope documents the subset caveat."""
    slugs = [o["slug"] for o in built.orgs]
    assert slugs == sorted(slugs)
    assert "subset" in built.doc["description"].lower()
    assert built.doc["sources"]


def test_uk_nominet_plays_all_three_iana_roles(built):
    """One org filling multiple roles is captured natively (not duplicated)."""
    uk = built.tlds["uk"]["annotations"]
    for role in ("sponsor", "admin", "tech"):
        assert uk[f"iana_{role}_slug"] == "nominet"

    nominet_iana = built.by_slug["nominet"]["roles"]["iana"]
    for role in ("sponsor", "admin", "tech"):
        assert "uk" in nominet_iana[role]


def test_uk_nameservers_span_distinct_operators(built):
    """Distinct infra operators are kept distinct, not collapsed."""
    slugs = set(built.tlds["uk"]["annotations"]["as_org_slugs"])

    assert {"nominet", "ultradns"} <= slugs


def test_knipp_spans_iana_tech_and_asn_operator(built):
    """A single org spanning an IANA role and the ASN role is one record."""
    roles = built.by_slug["knipp-medien"]["roles"]

    assert roles["iana"]["tech"]
    assert roles["asn"]["operator"]


def test_governance_body_is_ordinary_record(built):
    """ICANN's EBERO program is an ordinary record using normal role buckets."""
    ebero = built.by_slug["icann-ebero"]

    assert ebero.get("roles"), "expected the governance body to carry real roles"
    assert "kind" not in ebero
    assert "tld_count" not in ebero
