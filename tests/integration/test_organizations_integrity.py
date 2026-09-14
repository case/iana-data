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
import os
from types import SimpleNamespace

import pytest
from _pytest.outcomes import Failed, Skipped, XFailed

from src.parse.organizations import build_resolver, parse_organizations_manual
from src.utilities.download import get_iptoasn_path
from tests.conftest import asn_artifact_is_usable, build_into
from tests.integration.asn_drift import (
    ASN_DRIFT,
    classify_missing_asn_role,
    raw_org_strings,
    split_missing_slugs,
    split_orphans,
    split_unmatched_source_names,
    warn_drift,
)
from tests.parse.test_organizations_archive_migration import unmigrate

# Annotation prefix -> (source bucket, role) for the scalar registry positions.
SCALAR_ROLES = [
    ("iana_sponsor", "iana", "sponsor"),
    ("iana_admin", "iana", "admin"),
    ("iana_tech", "iana", "tech"),
    ("icann_registry_operator", "icann", "registry_operator"),
]


def _require_iptoasn_source() -> bool:
    """Whether a fresh ASN build is possible; fail in CI unless the nightly opted out.

    ASN_ARTIFACT_OPTIONAL is how the nightly says its health gate already chose a
    preserve build. The structural assertions still run, against the preserved
    graph. Why: docs/plans/current/2026-09-11-asn-drift-automation.md
    """
    if asn_artifact_is_usable():
        return True
    if os.environ.get("ASN_ARTIFACT_OPTIONAL"):
        return False

    reason = (
        f"{get_iptoasn_path()} is missing, so a fresh build carries no ASN data. "
        "Fetch it with:\n    make download-iptoasn"
    )
    if os.environ.get("CI"):
        pytest.fail(f"{reason}\n\nCI downloads this artifact; check that step.")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One fresh build, yielding the parsed tlds.json and organizations.json.

    Falls back to a preserve build when the artifact is absent and the nightly
    opted out, so the structural assertions below still run.
    """
    fresh = _require_iptoasn_source()
    tmp = tmp_path_factory.mktemp("orgs_integrity")
    paths = build_into(tmp, preserve_asn=not fresh)

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
    """Every curated org resolves to a real role (no orphan identity records).

    An org warns instead when only its asn names are asserted, seeded or
    archived, and none of its resolution keys matches current data.
    """
    raw = raw_org_strings(built.tlds.values())
    hard, drift = split_orphans(built.orgs, raw)

    if drift:
        warn_drift(f"orgs resolving to nothing, asn names only: {drift}")
    assert hard == [], (
        f"orgs in organizations.json that map to zero TLDs: {hard}. "
        "Either the org's asn names don't match live data, or it should be removed."
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


def _diagnose_unmatched(unmatched, raw_tlds, headline):
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
    return f"{headline}:\n" + "\n".join(lines)


# archived.asn, not aliases: an alias resolves in every bucket, so retiring an
# asn label there widens it. Why: docs/memory/log/2026-09-12-archived-bucket.md
_HARD_ADVICE = (
    "source_names strings not found in any tlds.json raw value for that "
    "source (fix the seed, or retire it to archived for that source)"
)
_DRIFT_ADVICE = (
    "asn source_names matching no current tlds.json raw value (tolerated). "
    "Leaving an absent asn seed in place is valid, and so is retiring it to "
    "archived.asn, which keeps resolving it in the asn bucket. An org left "
    "with neither an asn source_name nor an archived.asn entry fails instead"
)


def test_source_names_appear_in_raw_data(built):
    """Every iana/icann source_names string must occur as a raw value in tlds.json
    for that source. A string matching nothing is a stale or typo'd curation entry.
    An unmatched asn string warns instead: those labels come and go upstream."""
    raw_tlds = raw_org_strings(built.tlds.values())

    hard, drift = split_unmatched_source_names(built.orgs, raw_tlds)

    if drift:
        warn_drift(_diagnose_unmatched(drift, raw_tlds, _DRIFT_ADVICE))
    assert hard == [], _diagnose_unmatched(hard, raw_tlds, _HARD_ADVICE)


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
    entry = built.tlds["uk"]
    slugs = set(entry.get("annotations", {}).get("as_org_slugs", []))
    missing = sorted({"nominet", "ultradns"} - slugs)
    hard, drift = split_missing_slugs(missing, built.by_slug, raw_org_strings([entry]))

    if drift:
        warn_drift(f"uk operators whose asn names match nothing: {drift}")
    assert hard == [], f"uk should span distinct operators, missing: {hard}"


def test_knipp_spans_iana_tech_and_asn_operator(built):
    """A single org spanning an IANA role and the ASN role is one record."""
    org = built.by_slug["knipp-medien"]
    roles = org.get("roles", {})

    assert roles.get("iana", {}).get("tech"), "knipp should hold an iana tech role"

    if not roles.get("asn", {}).get("operator"):
        raw = raw_org_strings(built.tlds.values())
        assert classify_missing_asn_role(org, raw) == ASN_DRIFT, (
            "knipp lost its asn operator role for a reason other than asn drift"
        )
        warn_drift("knipp asn operator role absent: no asn name matches")


def test_governance_body_is_ordinary_record(built):
    """ICANN's EBERO program is an ordinary record using normal role buckets."""
    ebero = built.by_slug["icann-ebero"]

    assert ebero.get("roles"), "expected the governance body to carry real roles"
    assert "kind" not in ebero
    assert "tld_count" not in ebero


def test_the_archive_migration_preserves_every_live_resolution(built):
    """No raw value that resolves today changes the slug it resolves to.

    Live-data half of the migration check; lifetime note in the sibling in tests/parse.
    """
    seed = parse_organizations_manual()
    after = build_resolver(seed)
    before = build_resolver([unmigrate(org) for org in seed])

    raw = raw_org_strings(built.tlds.values())
    rebound = []
    for source, values in raw.items():
        for value in values:
            was, now = before.resolve(source, value), after.resolve(source, value)
            was_slug = was["slug"] if was else None
            now_slug = now["slug"] if now else None
            if was_slug != now_slug:
                rebound.append((source, value, was_slug, now_slug))

    assert rebound == [], f"live raw values whose slug changed: {rebound[:10]}"


def test_archived_entries_reach_the_published_artifact(built):
    """archived is consumer-visible: build_organizations_json copies every seed key."""
    verisign = built.by_slug["verisign"]

    archived = {e["name"] for e in verisign["archived"]["asn"]}
    assert "VRSN-AC28" in archived
    assert "VRSN-AC28" not in verisign.get("aliases", [])


def _returns_without_a_pytest_outcome(call):
    """Call ``call`` and reject a skip or xfail, which both exit green.

    The guard's fallback branch returning False is the whole contract; a skip
    there takes the structural assertions with it, silently.
    """
    try:
        return call()
    except (Skipped, XFailed) as exc:
        pytest.fail(f"{type(exc).__name__} instead of a return: {exc}")


class TestArtifactGuardHonoursTheNightlyBuildMode:
    """M3: a missing artifact must not block the nightly once it fell back."""

    def test_a_rejected_artifact_selects_preserve_even_when_present(
        self, monkeypatch, tmp_path
    ):
        """The gate's verdict outranks mere existence; rereading it is worse."""
        artifact = tmp_path / "ip2asn-combined.tsv.gz"
        artifact.write_bytes(b"present but rejected")
        monkeypatch.setattr("tests.conftest.get_iptoasn_path", lambda: artifact)
        monkeypatch.delenv("ASN_ARTIFACT_OPTIONAL", raising=False)
        assert artifact.exists()
        assert asn_artifact_is_usable() is True, "guards the rest of this test"

        monkeypatch.setenv("ASN_ARTIFACT_OPTIONAL", "1")

        assert asn_artifact_is_usable() is False

    def test_it_fails_in_ci_by_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("ASN_ARTIFACT_OPTIONAL", raising=False)
        # Both names: the guard resolves presence through tests.conftest and
        # renders its message from its own import.
        for target in (
            "tests.conftest.get_iptoasn_path",
            "tests.integration.test_organizations_integrity.get_iptoasn_path",
        ):
            monkeypatch.setattr(target, lambda: tmp_path / "absent.gz")

        # A skip here exits green exactly like a pass, so the skip is asserted
        # against explicitly rather than left to pytest.raises.
        try:
            _require_iptoasn_source()
        except Skipped as exc:
            pytest.fail(f"guard skipped instead of failing in CI: {exc}")
        except Failed as exc:
            # type, not isinstance: XFailed subclasses Failed and would pass.
            assert type(exc) is Failed, f"guard raised {type(exc).__name__}"
            assert "missing" in str(exc)
        else:
            pytest.fail("guard neither failed nor skipped with no artifact in CI")

    def test_it_reports_a_preserve_build_when_the_nightly_opted_out(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("ASN_ARTIFACT_OPTIONAL", "1")
        # Both names: the guard resolves presence through tests.conftest and
        # renders its message from its own import.
        for target in (
            "tests.conftest.get_iptoasn_path",
            "tests.integration.test_organizations_integrity.get_iptoasn_path",
        ):
            monkeypatch.setattr(target, lambda: tmp_path / "absent.gz")

        assert _returns_without_a_pytest_outcome(_require_iptoasn_source) is False
