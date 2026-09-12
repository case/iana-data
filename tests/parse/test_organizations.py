"""Tests for the organizations parser and resolver."""

import json

import pytest

from src.parse.organizations import (
    build_resolver,
    parse_organizations_manual,
    validate_organizations,
)


def _resolved_slug(resolver, source, name):
    """Resolve and return the slug, asserting the lookup hit (keeps tests type-safe)."""
    org = resolver.resolve(source, name)
    assert org is not None, f"{name!r} should resolve in {source}"
    return org["slug"]


def _org(
    slug, display_name, *, iana=None, icann=None, asn=None, aliases=None, archived=None
):
    source_names = {}
    if iana is not None:
        source_names["iana"] = iana
    if icann is not None:
        source_names["icann"] = icann
    if asn is not None:
        source_names["asn"] = asn
    record = {
        "display_name": display_name,
        "slug": slug,
        "source_names": source_names,
        "aliases": aliases or [],
        "homepage": None,
    }
    if archived is not None:
        record["archived"] = archived
    return record


def _archived(*names, on="2026-09-12"):
    """Well-formed archived entries for the given names."""
    return [{"name": name, "archived_on": on} for name in names]


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


class TestArchivedResolvesInItsOwnBucketOnly:
    """M2's central property: archiving narrows where a label resolves."""

    def test_archived_name_resolves_in_its_own_bucket_and_no_other(self):
        """The difference from aliases, which fall back into every bucket."""
        orgs = [
            _org(
                "verisign",
                "VeriSign",
                asn=["VRSN-AC50-340"],
                archived={"asn": _archived("VRSN-AC28")},
            )
        ]
        resolver = build_resolver(orgs)

        assert _resolved_slug(resolver, "asn", "VRSN-AC28") == "verisign"
        assert resolver.resolve("iana", "VRSN-AC28") is None
        assert resolver.resolve("icann", "VRSN-AC28") is None

    def test_an_alias_still_resolves_everywhere(self):
        orgs = [
            _org("verisign", "VeriSign", asn=["LIVE"], aliases=["Network Solutions"])
        ]
        resolver = build_resolver(orgs)

        for source in ("iana", "icann", "asn"):
            assert _resolved_slug(resolver, source, "Network Solutions") == "verisign"

    def test_archiving_in_one_bucket_leaves_the_others_free(self):
        """Another org may claim the same string in a bucket the archive vacated."""
        orgs = [
            _org(
                "verisign", "VeriSign", asn=["LIVE"], archived={"asn": _archived("X")}
            ),
            _org("other", "Other", iana=["X"]),
        ]
        resolver = build_resolver(orgs)

        assert resolver.collisions == []
        assert _resolved_slug(resolver, "asn", "X") == "verisign"
        assert _resolved_slug(resolver, "iana", "X") == "other"

    def test_a_name_in_both_source_names_and_archived_is_not_a_collision(self):
        """Same slug claims it twice, so first-claimant-wins never fires."""
        orgs = [_org("acme", "Acme", asn=["DUP"], archived={"asn": _archived("DUP")})]
        resolver = build_resolver(orgs)

        assert resolver.collisions == []
        assert _resolved_slug(resolver, "asn", "DUP") == "acme"


def _keys(orgs):
    """The resolver's complete key space as ``{(source, name): slug}``."""
    resolver = build_resolver(orgs)
    return {
        (source, name): org["slug"]
        for source, names in resolver.by_source.items()
        for name, org in names.items()
    }


class TestBuildResolverSurvivesAMalformedArchive:
    """A curation error must fail a test, not crash the build.

    Key-set equality, not one absent name, so a bad name cannot hide as its own key.
    """

    @pytest.mark.parametrize(
        "archived",
        [
            [],
            "asn",
            {"asn": None},
            {"asn": "VRSN-AC28"},
            {"asn": ["VRSN-AC28"]},
            {"asn": [{"name": ["VRSN-AC28"], "archived_on": "2026-09-12"}]},
            {"asn": [{"name": 123, "archived_on": "2026-09-12"}]},
            {"asn": [{"name": "", "archived_on": "2026-09-12"}]},
        ],
        ids=[
            "list",
            "string",
            "null-bucket",
            "string-bucket",
            "bare-string-entry",
            "unhashable-name",
            "non-string-name",
            "empty-name",
        ],
    )
    def test_malformed_archive_contributes_no_keys(self, archived):
        baseline = _keys([_org("acme", "Acme", asn=["LIVE"])])

        assert (
            _keys([_org("acme", "Acme", asn=["LIVE"], archived=archived)]) == baseline
        )

    @pytest.mark.parametrize(
        "entry",
        [
            {"name": "VRSN-AC28"},
            {"name": "VRSN-AC28", "archived_on": "2026-13-45"},
            {"name": "VRSN-AC28", "archived_on": "20260912"},
            {"name": "VRSN-AC28", "archived_on": "2026-09-12", "why": "flapping"},
        ],
        ids=["missing-date", "impossible-date", "unpadded-date", "unknown-key"],
    )
    def test_a_valid_name_with_invalid_metadata_contributes_no_key(self, entry):
        """The whole entry must be usable, not just its name."""
        baseline = _keys([_org("acme", "Acme", asn=["LIVE"])])
        orgs = [_org("acme", "Acme", asn=["LIVE"], archived={"asn": [entry]})]

        assert _keys(orgs) == baseline

    def test_a_null_archive_contributes_no_keys(self):
        """Set explicitly: _org omits the key entirely for a None argument."""
        record = _org("acme", "Acme", asn=["LIVE"])
        record["archived"] = None

        assert _keys([record]) == _keys([_org("acme", "Acme", asn=["LIVE"])])


class TestValidateOrganizations:
    """The seed's archived buckets, policed the way collisions already are."""

    @pytest.mark.parametrize(
        "record",
        [
            _org(
                "verisign",
                "VeriSign",
                asn=["VRSN-AC50-340"],
                archived={"asn": _archived("VRSN-AC28", "HGTLD")},
            ),
            _org("acme", "Acme", asn=["LIVE"]),
        ],
        ids=["with-archive", "without-archive"],
    )
    def test_a_clean_record_has_no_problems(self, record):
        assert validate_organizations([record]) == []

    def test_display_name_may_also_be_an_archived_name(self):
        """nic-chile seeds its own display_name as an asn label; archiving it is legal."""
        record = _org(
            "nic-chile", "NIC Chile", archived={"asn": _archived("NIC Chile")}
        )

        assert validate_organizations([record]) == []

    @pytest.mark.parametrize(
        "archived,expected",
        [
            ({"ans": _archived("X")}, "is not one of"),
            ({"asn": "X"}, "expected a list"),
            ({"asn": ["X"]}, "expected an object"),
            ({"asn": [{"name": "X"}]}, "missing ['archived_on']"),
            ({"asn": [{"archived_on": "2026-09-12"}]}, "missing ['name']"),
            (
                {"asn": [{"name": "X", "archived_on": "2026-09-12", "why": "z"}]},
                "unknown key(s) ['why']",
            ),
            ({"asn": [{"name": "", "archived_on": "2026-09-12"}]}, "non-empty string"),
            ({"asn": [{"name": 1, "archived_on": "2026-09-12"}]}, "non-empty string"),
            ({"asn": _archived("X") + _archived("X")}, "twice"),
        ],
        ids=[
            "unknown-bucket",
            "bucket-not-a-list",
            "entry-not-an-object",
            "missing-date",
            "missing-name",
            "unknown-key",
            "empty-name",
            "non-string-name",
            "duplicate-name",
        ],
    )
    def test_shape_problems_are_reported(self, archived, expected):
        record = _org("acme", "Acme", asn=["LIVE"], archived=archived)

        problems = validate_organizations([record])

        assert any(expected in p for p in problems), problems

    def test_archived_that_is_not_a_mapping_is_reported(self):
        record = _org("acme", "Acme", asn=["LIVE"])
        record["archived"] = ["VRSN-AC28"]

        problems = validate_organizations([record])

        assert any("expected an object" in p for p in problems), problems

    @pytest.mark.parametrize(
        "value",
        ["20260912", "2026-9-1", "2026-13-01", "2026-02-30", "2026-09-12T00:00:00", ""],
        ids=["compact", "unpadded", "bad-month", "bad-day", "datetime", "empty"],
    )
    def test_archived_on_must_be_a_real_padded_iso_date(self, value):
        record = _org("acme", "Acme", archived={"asn": _archived("X", on=value)})

        problems = validate_organizations([record])

        assert any("archived_on" in p for p in problems), problems

    def test_a_name_in_both_source_names_and_archived_is_reported(self):
        record = _org("acme", "Acme", asn=["DUP"], archived={"asn": _archived("DUP")})

        problems = validate_organizations([record])

        assert any("also a source_name" in p for p in problems), problems

    def test_a_name_in_both_aliases_and_archived_is_reported(self):
        """An alias resolves everywhere, so the archive entry would be inert."""
        record = _org(
            "acme", "Acme", aliases=["OLD"], archived={"asn": _archived("OLD")}
        )

        problems = validate_organizations([record])

        assert any("also an alias" in p for p in problems), problems

    def test_the_same_name_archived_in_two_buckets_is_fine(self):
        record = _org(
            "acme", "Acme", archived={"asn": _archived("X"), "iana": _archived("X")}
        )

        assert validate_organizations([record]) == []

    def test_the_committed_seed_is_clean(self):
        assert validate_organizations(parse_organizations_manual()) == []

    @pytest.mark.parametrize(
        "record",
        [
            "not-a-record",
            {"slug": "a", "display_name": "A", "aliases": None},
            {"slug": "a", "display_name": "A", "source_names": []},
            {"slug": "a", "display_name": "A", "archived": {"asn": [None]}},
            {
                "slug": "a",
                "display_name": "A",
                "source_names": {"asn": None},
                "archived": {"asn": _archived("X")},
            },
        ],
        ids=[
            "not-an-object",
            "null-aliases",
            "source-names-not-an-object",
            "null-entry",
            "null-source-names-bucket",
        ],
    )
    def test_a_malformed_record_is_reported_never_raised(self, record):
        """The parser calls this, so a raise here would break the build instead."""
        problems = validate_organizations([record])

        assert problems, "a malformed record should be reported, not passed over"

    def test_a_malformed_record_survives_the_parser(self, tmp_path):
        path = tmp_path / "organizations.json"
        path.write_text(
            json.dumps([{"slug": "a", "display_name": "A", "aliases": None}])
        )

        assert parse_organizations_manual(path) == [
            {"slug": "a", "display_name": "A", "aliases": None}
        ]
