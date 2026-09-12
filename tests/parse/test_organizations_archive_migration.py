"""Acceptance test for the 2026-09-12 migration out of `aliases`.

Six ASN labels left `aliases`, which resolve in every bucket, for an asn-scoped
field: five into `archived.asn` because no raw value matches them, and `HGTLD`
into `source_names.asn` because it does. Either way the label stops resolving
under `iana` and `icann`, so this compares the complete before/after
(source, name) -> slug mapping against an explicit allowlist rather than
sampling live values.

Lifetime: this pins one historical migration. If a live raw value ever exercises
one of the removed cross-bucket mappings, the honest response is to retire this
test, not to revert the migration. Rationale:
docs/memory/log/2026-09-12-archived-bucket.md
"""

import pytest

from src.parse.organizations import (
    SOURCES,
    build_resolver,
    parse_organizations_manual,
)

# Labels with no raw match, evidenced from the memory log rather than inferred
# from present liveness.
ARCHIVED: dict[str, tuple[str, ...]] = {
    "verisign": ("VERISIGN-AS", "VGRS-AC25", "VRSN-AC28"),
    "cloudflare": ("CLOUDFLARENET",),
    "teleinfo": ("CAICTNET Chinese Academy of Telecommunication Research",),
}

# Live on com/edu/net in the pinned artifact, so it is seeded, not archived.
RESEEDED: dict[str, tuple[str, ...]] = {"verisign": ("HGTLD",)}

MIGRATED: dict[str, tuple[str, ...]] = {
    slug: (*ARCHIVED.get(slug, ()), *RESEEDED.get(slug, ()))
    for slug in ARCHIVED.keys() | RESEEDED.keys()
}

# The justified removals: each label stops resolving in the two buckets it never
# belonged to. Its asn resolution is preserved by the field it moved into.
EXPECTED_REMOVALS: set[tuple[str, str, str]] = {
    (source, name, slug)
    for slug, names in MIGRATED.items()
    for name in names
    for source in ("iana", "icann")
}


def unmigrate(org: dict) -> dict:
    """Reverse this one migration on a record, leaving every other field live."""
    names = MIGRATED.get(org["slug"])
    if not names:
        return org
    reverted = dict(org)
    reverted["aliases"] = sorted([*org.get("aliases", []), *names])
    reverted["source_names"] = {
        source: [n for n in seeded if n not in names]
        for source, seeded in org.get("source_names", {}).items()
    }
    archived = {
        source: [e for e in entries if e["name"] not in names]
        for source, entries in org.get("archived", {}).items()
    }
    reverted["archived"] = {s: e for s, e in archived.items() if e}
    return reverted


def _key_map(orgs: list[dict]) -> dict[tuple[str, str], str]:
    """The resolver's complete key space as ``{(source, name): slug}``."""
    resolver = build_resolver(orgs)
    return {
        (source, name): org["slug"]
        for source in SOURCES
        for name, org in resolver.by_source[source].items()
    }


@pytest.fixture(scope="module")
def seed():
    return parse_organizations_manual()


@pytest.fixture(scope="module")
def maps(seed):
    """The committed seed's key map, and the same seed with the migration undone."""
    assert seed, "expected a non-empty seed"
    return _key_map([unmigrate(org) for org in seed]), _key_map(seed)


def _asn_fields(org: dict) -> tuple[set[str], set[str]]:
    """The org's seeded and archived asn names."""
    seeded = set(org.get("source_names", {}).get("asn", []))
    archived = {e["name"] for e in org.get("archived", {}).get("asn", [])}
    return seeded, archived


def test_no_migrated_label_remains_an_alias(seed):
    """The durable half of the migration: nothing may put these back in aliases."""
    by_slug = {org["slug"]: org for org in seed}

    for slug, names in MIGRATED.items():
        assert not set(names) & set(by_slug[slug].get("aliases", []))


def test_each_migrated_label_sits_in_exactly_one_asn_field(seed):
    """Both fields at once would make the archive entry inert; neither loses the label."""
    by_slug = {org["slug"]: org for org in seed}

    for slug, names in MIGRATED.items():
        seeded, archived = _asn_fields(by_slug[slug])
        for name in names:
            assert (name in seeded) != (name in archived), f"{slug}/{name}"


def test_each_label_is_in_the_field_the_migration_chose(seed):
    """Pins the 2026-09-12 destinations; M4 archiving a seeded label retires this.

    Why the split: docs/memory/log/2026-09-12-archived-bucket.md
    """
    by_slug = {org["slug"]: org for org in seed}

    for slug, names in ARCHIVED.items():
        assert set(names) <= _asn_fields(by_slug[slug])[1], f"{slug} not archived"
    for slug, names in RESEEDED.items():
        assert set(names) <= _asn_fields(by_slug[slug])[0], f"{slug} not seeded"


def test_the_migration_removes_exactly_the_allowlisted_keys(maps):
    before, after = maps

    removed = {
        (source, name, before[key])
        for key in set(before) - set(after)
        for source, name in [key]
    }

    assert removed == EXPECTED_REMOVALS
    # A key only `after` holds means unmigrate dropped one it should have kept.
    assert sorted(set(after) - set(before)) == []


def test_every_migrated_label_still_resolves_in_the_asn_bucket(maps):
    """The point of the migration: attribution survives the narrowing."""
    _, after = maps

    for slug, names in MIGRATED.items():
        for name in names:
            assert after.get(("asn", name)) == slug
