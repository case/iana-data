"""Tests for the organizations parser and resolver."""

import json

from src.parse.organizations import (
    build_resolver,
    parse_organizations_manual,
)


def _resolved_slug(resolver, source, name):
    """Resolve and return the slug, asserting the lookup hit (keeps tests type-safe)."""
    org = resolver.resolve(source, name)
    assert org is not None, f"{name!r} should resolve in {source}"
    return org["slug"]


def _org(slug, display_name, *, iana=None, icann=None, asn=None, aliases=None):
    source_names = {}
    if iana is not None:
        source_names["iana"] = iana
    if icann is not None:
        source_names["icann"] = icann
    if asn is not None:
        source_names["asn"] = asn
    return {
        "display_name": display_name,
        "slug": slug,
        "source_names": source_names,
        "aliases": aliases or [],
        "homepage": None,
    }


def test_parse_organizations_manual_returns_records():
    """The committed seed parses into identity records with the core fields."""
    orgs = parse_organizations_manual()

    assert isinstance(orgs, list)
    assert orgs, "expected a non-empty seed"
    for org in orgs:
        assert org["display_name"]
        assert org["slug"]
        assert "source_names" in org


def test_parse_organizations_manual_missing_file_returns_empty(tmp_path):
    """A missing file yields an empty list, not an error."""
    assert parse_organizations_manual(tmp_path / "nope.json") == []


def test_parse_organizations_manual_non_array_returns_empty(tmp_path):
    """A non-array JSON document yields an empty list."""
    path = tmp_path / "organizations.json"
    path.write_text(json.dumps({"not": "a list"}))

    assert parse_organizations_manual(path) == []


def test_build_resolver_resolves_per_bucket():
    """A raw string resolves to its org within the matching source bucket."""
    orgs = [
        _org(
            "identity-digital",
            "Identity Digital",
            iana=["Binky Moon, LLC"],
            icann=["Dog Beach, LLC"],
            asn=["AFILIAS-SECONDARY-DNS"],
        ),
    ]
    resolver = build_resolver(orgs)

    assert _resolved_slug(resolver, "iana", "Binky Moon, LLC") == "identity-digital"
    assert _resolved_slug(resolver, "icann", "Dog Beach, LLC") == "identity-digital"
    assert (
        _resolved_slug(resolver, "asn", "AFILIAS-SECONDARY-DNS") == "identity-digital"
    )
    # A name only present in the iana bucket does not resolve under icann.
    assert resolver.resolve("icann", "Binky Moon, LLC") is None


def test_build_resolver_resolves_via_display_name_and_alias_fallback():
    """display_name and aliases match in every bucket as a fallback."""
    orgs = [
        _org(
            "verisign",
            "Verisign",
            iana=["VeriSign Global Registry Services"],
            aliases=["Network Solutions"],
        )
    ]
    resolver = build_resolver(orgs)

    assert _resolved_slug(resolver, "iana", "Verisign") == "verisign"
    assert _resolved_slug(resolver, "icann", "Verisign") == "verisign"
    assert _resolved_slug(resolver, "iana", "Network Solutions") == "verisign"


def test_build_resolver_detects_collision():
    """The same string claimed by two orgs in one bucket is a recorded collision."""
    orgs = [
        _org("org-a", "Org A", iana=["Shared Name, Inc."]),
        _org("org-b", "Org B", iana=["Shared Name, Inc."]),
    ]
    resolver = build_resolver(orgs)

    assert resolver.collisions, "expected a collision to be recorded"
    bucket, name, kept, dropped = resolver.collisions[0]
    assert bucket == "iana"
    assert name == "Shared Name, Inc."
    assert kept == "org-a"  # first claimant wins, deterministically
    assert dropped == "org-b"
    assert _resolved_slug(resolver, "iana", "Shared Name, Inc.") == "org-a"


def test_resolver_returns_none_for_unknown_and_empty():
    """Unknown names and empty/None inputs resolve to None."""
    resolver = build_resolver([_org("x", "X", iana=["X Corp"])])

    assert resolver.resolve("iana", "Unknown Co.") is None
    assert resolver.resolve("iana", "") is None
    assert resolver.resolve("iana", None) is None
    assert resolver.resolve("nonsense-bucket", "X Corp") is None
