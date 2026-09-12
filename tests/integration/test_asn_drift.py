"""Unit tests for the ASN drift policy that relaxes four live-data assertions.

Driven entirely from synthetic graphs: the live seed cannot reach most of these
states, and a fixture is the only way to exercise the warn path before drift
actually happens.
"""

from types import SimpleNamespace

import pytest

import tests.integration.test_organizations_integrity as integrity
from tests.integration.asn_drift import (
    ASN_DRIFT,
    HARD,
    AsnDriftWarning,
    OrgRecord,
    RawStrings,
    classify_absence,
    classify_missing_asn_role,
    raw_org_strings,
    split_missing_slugs,
    split_orphans,
    split_unmatched_source_names,
    warn_drift,
)


def org(
    slug: str = "acme",
    display_name: str = "Acme",
    source_names: dict[str, list[str]] | None = None,
    aliases: list[str] | None = None,
    archived: dict | None = None,
) -> OrgRecord:
    """An organizations.json seed record with the fields the resolver reads."""
    record = {
        "slug": slug,
        "display_name": display_name,
        "source_names": {} if source_names is None else source_names,
        "aliases": [] if aliases is None else aliases,
    }
    if archived is not None:
        record["archived"] = archived
    return record


def archive(*names: str, on: str = "2026-09-12") -> list[dict]:
    """Well-formed archived entries for the given names."""
    return [{"name": name, "archived_on": on} for name in names]


def raw(iana=(), icann=(), asn=()) -> RawStrings:
    return {
        "iana": {name: {"tld"} for name in iana},
        "icann": {name: {"tld"} for name in icann},
        "asn": {name: {"tld"} for name in asn},
    }


def tld_entry(tld="uk", iana=None, icann=None, nameservers=None) -> dict:
    entry: dict = {"tld": tld, "orgs": {}}
    if iana:
        entry["orgs"]["iana"] = iana
    if icann:
        entry["orgs"]["icann"] = icann
    if nameservers is not None:
        entry["nameservers"] = nameservers
    return entry


class TestRawOrgStrings:
    def test_collects_iana_roles_and_maps_them_to_their_tld(self):
        entries = [tld_entry(iana={"sponsor": "S", "admin": "A", "tech": "T"})]

        assert raw_org_strings(entries)["iana"] == {
            "S": {"uk"},
            "A": {"uk"},
            "T": {"uk"},
        }

    def test_collects_icann_registry_operator(self):
        entries = [tld_entry(icann={"registry_operator": "RO"})]

        assert raw_org_strings(entries)["icann"] == {"RO": {"uk"}}

    def test_collects_as_org_from_both_address_families(self):
        entries = [
            tld_entry(
                nameservers=[
                    {"ipv4": [{"as_org": "V4"}], "ipv6": [{"as_org": "V6"}]},
                ]
            )
        ]

        assert raw_org_strings(entries)["asn"] == {"V4": {"uk"}, "V6": {"uk"}}

    def test_one_string_on_several_tlds_accumulates_them(self):
        entries = [
            tld_entry(tld="uk", nameservers=[{"ipv4": [{"as_org": "X"}]}]),
            tld_entry(tld="com", nameservers=[{"ipv4": [{"as_org": "X"}]}]),
        ]

        assert raw_org_strings(entries)["asn"]["X"] == {"uk", "com"}

    def test_empty_input_yields_every_bucket_empty(self):
        assert raw_org_strings([]) == {"iana": {}, "icann": {}, "asn": {}}

    def test_missing_optional_keys_are_skipped_not_crashed(self):
        entries = [{"tld": "uk"}, tld_entry(nameservers=[{}])]

        assert raw_org_strings(entries) == {"iana": {}, "icann": {}, "asn": {}}

    def test_null_as_org_is_not_recorded(self):
        entries = [tld_entry(nameservers=[{"ipv4": [{"as_org": None}]}])]

        assert raw_org_strings(entries)["asn"] == {}


class TestClassifyAbsence:
    def test_only_asn_names_and_none_match_is_drift(self):
        assert classify_absence(org(source_names={"asn": ["GONE"]}), raw()) == ASN_DRIFT

    def test_unmatched_iana_name_is_hard(self):
        assert classify_absence(org(source_names={"iana": ["GONE"]}), raw()) == HARD

    def test_unmatched_icann_name_is_hard(self):
        assert classify_absence(org(source_names={"icann": ["GONE"]}), raw()) == HARD

    def test_mixed_buckets_all_unmatched_is_hard(self):
        record = org(source_names={"asn": ["GONE"], "iana": ["ALSO"]})

        assert classify_absence(record, raw()) == HARD

    def test_a_live_source_name_with_a_missing_relationship_is_hard(self):
        record = org(source_names={"asn": ["LIVE", "GONE"]})

        assert classify_absence(record, raw(asn=["LIVE"])) == HARD

    def test_a_live_display_name_is_hard(self):
        record = org(display_name="Acme", source_names={"asn": ["GONE"]})

        assert classify_absence(record, raw(iana=["Acme"])) == HARD

    def test_a_live_alias_is_hard(self):
        record = org(source_names={"asn": ["GONE"]}, aliases=["OLD"])

        assert classify_absence(record, raw(asn=["OLD"])) == HARD

    def test_empty_source_names_mapping_is_hard(self):
        assert classify_absence(org(source_names={}), raw()) == HARD

    def test_asn_bucket_present_but_empty_is_hard(self):
        assert classify_absence(org(source_names={"asn": []}), raw()) == HARD

    def test_every_bucket_present_but_empty_is_hard(self):
        record = org(source_names={"iana": [], "icann": [], "asn": []})

        assert classify_absence(record, raw()) == HARD

    def test_unrecognized_bucket_is_hard_not_drift(self):
        assert classify_absence(org(source_names={"ans": ["TYPO"]}), raw()) == HARD


class TestClassifyMissingAsnRole:
    """Scoped to the asn bucket: an org keeps other roles while losing its asn one."""

    def test_live_iana_key_does_not_make_an_absent_asn_label_hard(self):
        record = org(source_names={"iana": ["LIVE"], "asn": ["GONE"]})

        assert classify_missing_asn_role(record, raw(iana=["LIVE"])) == ASN_DRIFT

    def test_live_asn_key_is_hard(self):
        record = org(source_names={"iana": ["LIVE"], "asn": ["STILL", "GONE"]})

        assert (
            classify_missing_asn_role(record, raw(iana=["LIVE"], asn=["STILL"])) == HARD
        )

    def test_live_alias_in_the_asn_bucket_is_hard(self):
        record = org(source_names={"asn": ["GONE"]}, aliases=["OLD"])

        assert classify_missing_asn_role(record, raw(asn=["OLD"])) == HARD

    def test_live_display_name_in_the_asn_bucket_is_hard(self):
        """display_name resolves in every bucket, so a live one is a live asn key."""
        record = org(display_name="Acme", source_names={"asn": ["GONE"]})

        assert classify_missing_asn_role(record, raw(asn=["Acme"])) == HARD

    def test_org_asserting_no_asn_names_is_hard(self):
        record = org(source_names={"iana": ["LIVE"]})

        assert classify_missing_asn_role(record, raw(iana=["LIVE"])) == HARD

    def test_empty_asn_bucket_is_hard(self):
        assert classify_missing_asn_role(org(source_names={"asn": []}), raw()) == HARD

    def test_unknown_bucket_is_hard(self):
        record = org(source_names={"asn": ["GONE"], "ans": ["TYPO"]})

        assert classify_missing_asn_role(record, raw()) == HARD


class TestArchivedNamesAreAsnEvidence:
    """M2: an archived label is bucket-scoped evidence the other classifiers read."""

    def test_archived_only_org_with_nothing_live_warns(self):
        record = org(source_names={}, archived={"asn": archive("GONE")})

        assert classify_absence(record, raw()) == ASN_DRIFT

    def test_archived_only_org_missing_its_asn_role_warns(self):
        record = org(source_names={}, archived={"asn": archive("GONE")})

        assert classify_missing_asn_role(record, raw()) == ASN_DRIFT

    def test_a_live_archived_name_is_hard_in_its_own_bucket(self):
        """An archived label that came back resolves, so a missing role is a defect."""
        record = org(source_names={}, archived={"asn": archive("BACK")})

        assert classify_absence(record, raw(asn=["BACK"])) == HARD
        assert classify_missing_asn_role(record, raw(asn=["BACK"])) == HARD

    def test_an_archived_name_live_in_another_bucket_does_not_rescue_the_org(self):
        """archived.asn is indexed into asn only, unlike an alias."""
        record = org(source_names={}, archived={"asn": archive("GONE")})

        assert classify_absence(record, raw(iana=["GONE"])) == ASN_DRIFT

    def test_archived_iana_name_beside_archived_asn_is_hard(self):
        record = org(
            source_names={},
            archived={"asn": archive("GONE"), "iana": archive("ALSO")},
        )

        assert classify_absence(record, raw()) == HARD

    def test_empty_archived_asn_bucket_is_not_evidence(self):
        assert classify_absence(org(archived={"asn": []}), raw()) == HARD
        assert classify_missing_asn_role(org(archived={"asn": []}), raw()) == HARD

    def test_unknown_archived_bucket_is_hard(self):
        record = org(source_names={"asn": ["GONE"]}, archived={"ans": []})

        assert classify_absence(record, raw()) == HARD
        assert classify_missing_asn_role(record, raw()) == HARD


class TestMalformedArchiveIsNeverEvidence:
    """A bad seed must not manufacture the evidence that relaxes an assertion."""

    @pytest.mark.parametrize(
        "archived",
        [
            {"asn": [{"name": [], "archived_on": "2026-09-12"}]},
            {"asn": [{"name": "", "archived_on": "2026-09-12"}]},
            {"asn": [{"name": 123, "archived_on": "2026-09-12"}]},
            {"asn": ["VRSN-AC28"]},
            {"asn": {"name": "VRSN-AC28"}},
            {"asn": [{"name": "GONE"}]},
            {"asn": [{"name": "GONE", "archived_on": "2026-13-45"}]},
            {"asn": [{"name": "GONE", "archived_on": "20260912"}]},
            {"asn": [{"name": "GONE", "archived_on": "2026-09-12", "why": "x"}]},
        ],
        ids=[
            "unhashable",
            "empty",
            "non-string",
            "bare-string",
            "not-a-list",
            "missing-date",
            "impossible-date",
            "unpadded-date",
            "unknown-key",
        ],
    )
    def test_malformed_entries_do_not_warn(self, archived):
        record = org(source_names={}, archived=archived)

        assert classify_absence(record, raw()) == HARD
        assert classify_missing_asn_role(record, raw()) == HARD

    def test_archived_that_is_not_a_mapping_is_hard(self):
        record = org(source_names={"asn": ["GONE"]}, archived=None)
        record["archived"] = None

        assert classify_absence(record, raw()) == HARD
        assert classify_missing_asn_role(record, raw()) == HARD


class TestUnknownBucketIsAlwaysACurationError:
    def test_empty_unknown_bucket_beside_asn_drift_is_hard(self):
        record = org(source_names={"asn": ["GONE"], "ans": []})

        assert classify_absence(record, raw()) == HARD

    def test_empty_unknown_bucket_is_hard_for_the_asn_scoped_check(self):
        record = org(source_names={"asn": ["GONE"], "ans": []})

        assert classify_missing_asn_role(record, raw()) == HARD


class TestSplitUnmatchedSourceNames:
    def test_asn_miss_is_drift_and_iana_miss_is_hard(self):
        orgs = [
            org(slug="a", source_names={"asn": ["GONE"]}),
            org(slug="b", source_names={"iana": ["ALSO"]}),
        ]

        hard, drift = split_unmatched_source_names(orgs, raw())

        assert hard == [("b", "iana", "ALSO")]
        assert drift == [("a", "asn", "GONE")]

    def test_matching_names_produce_neither(self):
        orgs = [org(source_names={"asn": ["LIVE"]})]

        assert split_unmatched_source_names(orgs, raw(asn=["LIVE"])) == ([], [])

    def test_icann_miss_is_hard_not_drift(self):
        orgs = [org(slug="a", source_names={"icann": ["GONE"]})]

        hard, drift = split_unmatched_source_names(orgs, raw())

        assert hard == [("a", "icann", "GONE")]
        assert drift == []

    def test_one_org_can_contribute_to_both_lists(self):
        orgs = [org(slug="a", source_names={"asn": ["GONE"], "iana": ["ALSO"]})]

        hard, drift = split_unmatched_source_names(orgs, raw())

        assert hard == [("a", "iana", "ALSO")]
        assert drift == [("a", "asn", "GONE")]


class TestSplitOrphans:
    def test_asn_only_org_with_no_roles_is_drift(self):
        orgs = [org(slug="a", source_names={"asn": ["GONE"]})]

        assert split_orphans(orgs, raw()) == ([], ["a"])

    def test_org_with_roles_is_neither(self):
        record = org(slug="a", source_names={"asn": ["GONE"]})
        record["roles"] = {"asn": {"operator": ["uk"]}}

        assert split_orphans([record], raw()) == ([], [])

    def test_empty_source_names_orphan_is_hard(self):
        assert split_orphans([org(slug="a")], raw()) == (["a"], [])

    def test_iana_orphan_is_hard(self):
        orgs = [org(slug="a", source_names={"iana": ["GONE"]})]

        assert split_orphans(orgs, raw()) == (["a"], [])


class TestSplitMissingSlugs:
    def test_missing_asn_only_org_is_drift(self):
        by_slug = {"a": org(slug="a", source_names={"asn": ["GONE"]})}

        assert split_missing_slugs(["a"], by_slug, raw()) == ([], ["a"])

    def test_missing_iana_org_is_hard(self):
        by_slug = {"a": org(slug="a", source_names={"iana": ["GONE"]})}

        assert split_missing_slugs(["a"], by_slug, raw()) == (["a"], [])

    def test_slug_with_no_seed_record_is_hard(self):
        assert split_missing_slugs(["ghost"], {}, raw()) == (["ghost"], [])


class TestWarningIsVisible:
    def test_drift_warning_is_a_userwarning_subclass(self):
        assert issubclass(AsnDriftWarning, UserWarning)

    def test_warning_carries_the_labels_in_its_message(self):
        with pytest.warns(AsnDriftWarning, match="GONE"):
            warn_drift("asn labels absent: GONE")


class TestCallerPaths:
    """Drive the four real assertions with synthetic graphs.

    Helper-level tests miss the callers: two of the four index into optional
    structure, so a disappearance raises KeyError before any policy runs.
    """

    @staticmethod
    def built(tlds=None, orgs=None):
        orgs = orgs or []
        return SimpleNamespace(
            tlds=tlds or {},
            orgs=orgs,
            by_slug={o["slug"]: o for o in orgs},
        )

    def test_source_names_warns_on_asn_miss_and_passes(self):
        built = self.built(orgs=[org(slug="a", source_names={"asn": ["GONE"]})])

        with pytest.warns(AsnDriftWarning, match="GONE"):
            integrity.test_source_names_appear_in_raw_data(built)

    def test_source_names_still_fails_on_iana_miss(self):
        built = self.built(orgs=[org(slug="a", source_names={"iana": ["GONE"]})])

        with pytest.raises(AssertionError, match="GONE"):
            integrity.test_source_names_appear_in_raw_data(built)

    def test_source_names_fails_when_asn_drift_accompanies_an_icann_miss(self):
        built = self.built(
            orgs=[org(slug="a", source_names={"asn": ["GONE"], "icann": ["ALSO"]})]
        )

        with pytest.warns(AsnDriftWarning), pytest.raises(AssertionError, match="ALSO"):
            integrity.test_source_names_appear_in_raw_data(built)

    def test_source_names_still_fails_on_icann_miss(self):
        built = self.built(orgs=[org(slug="a", source_names={"icann": ["GONE"]})])

        with pytest.raises(AssertionError, match="GONE"):
            integrity.test_source_names_appear_in_raw_data(built)

    def test_source_names_fails_when_asn_drift_accompanies_an_iana_miss(self):
        built = self.built(
            orgs=[org(slug="a", source_names={"asn": ["GONE"], "iana": ["ALSO"]})]
        )

        with pytest.warns(AsnDriftWarning), pytest.raises(AssertionError, match="ALSO"):
            integrity.test_source_names_appear_in_raw_data(built)

    def test_orphans_warns_for_an_asn_only_org(self):
        built = self.built(orgs=[org(slug="a", source_names={"asn": ["GONE"]})])

        with pytest.warns(AsnDriftWarning, match="resolving to nothing"):
            integrity.test_every_org_has_at_least_one_role(built)

    def test_orphans_fails_for_empty_source_names(self):
        built = self.built(orgs=[org(slug="a", source_names={})])

        with pytest.raises(AssertionError, match="zero TLDs"):
            integrity.test_every_org_has_at_least_one_role(built)

    def test_orphans_fails_for_a_present_but_empty_asn_bucket(self):
        built = self.built(orgs=[org(slug="a", source_names={"asn": []})])

        with pytest.raises(AssertionError, match="zero TLDs"):
            integrity.test_every_org_has_at_least_one_role(built)

    def test_orphans_fails_when_a_fallback_key_matches_another_bucket(self):
        """Distinguishes the two predicates: the asn-scoped one would warn here."""
        record = org(slug="a", display_name="Acme", source_names={"asn": ["GONE"]})
        built = self.built(
            tlds={"uk": tld_entry(tld="uk", iana={"sponsor": "Acme"})}, orgs=[record]
        )

        with pytest.raises(AssertionError, match="zero TLDs"):
            integrity.test_every_org_has_at_least_one_role(built)

    def test_orphans_fails_for_a_mixed_iana_and_asn_org_with_both_absent(self):
        built = self.built(
            orgs=[org(slug="a", source_names={"iana": ["GONE"], "asn": ["ALSO"]})]
        )

        with pytest.raises(AssertionError, match="zero TLDs"):
            integrity.test_every_org_has_at_least_one_role(built)

    def test_orphans_fails_when_a_live_key_has_no_relationship(self):
        record = org(slug="a", source_names={"asn": ["LIVE"]})
        built = self.built(
            tlds={"uk": tld_entry(nameservers=[{"ipv4": [{"as_org": "LIVE"}]}])},
            orgs=[record],
        )

        with pytest.raises(AssertionError, match="zero TLDs"):
            integrity.test_every_org_has_at_least_one_role(built)

    def test_uk_warns_when_an_operator_label_left(self):
        """nominet keeps live iana keys on uk; only ultradns's asn label is gone."""
        nominet = org(
            slug="nominet",
            display_name="Nominet",
            source_names={"iana": ["Nominet"], "asn": ["NOMINET"]},
        )
        nominet["roles"] = {"iana": {"sponsor": ["uk"]}, "asn": {"operator": ["uk"]}}
        ultradns = org(
            slug="ultradns", display_name="UltraDNS", source_names={"asn": ["GONE"]}
        )
        built = self.built(
            tlds={
                "uk": tld_entry(
                    tld="uk",
                    iana={"sponsor": "Nominet"},
                    nameservers=[{"ipv4": [{"as_org": "NOMINET"}]}],
                )
            },
            orgs=[nominet, ultradns],
        )
        built.tlds["uk"]["annotations"] = {
            "iana_sponsor_slug": "nominet",
            "iana_sponsor_alias": "Nominet",
            "as_org_slugs": ["nominet"],
            "as_org_aliases": ["Nominet"],
        }

        with pytest.warns(AsnDriftWarning, match="ultradns"):
            integrity.test_uk_nameservers_span_distinct_operators(built)

    def test_uk_warns_for_an_operator_that_also_holds_a_live_iana_key(self):
        """The case the all-bucket predicate could never reach: nominet's own asn
        label leaves while its iana keys keep matching."""
        nominet = org(
            slug="nominet",
            display_name="Nominet",
            source_names={"iana": ["Nominet"], "asn": ["GONE"]},
        )
        nominet["roles"] = {"iana": {"sponsor": ["uk"]}}
        ultradns = org(
            slug="ultradns", display_name="UltraDNS", source_names={"asn": ["ALSOGONE"]}
        )
        built = self.built(
            tlds={"uk": tld_entry(tld="uk", iana={"sponsor": "Nominet"})},
            orgs=[nominet, ultradns],
        )
        built.tlds["uk"]["annotations"] = {
            "iana_sponsor_slug": "nominet",
            "iana_sponsor_alias": "Nominet",
        }

        with pytest.warns(AsnDriftWarning, match="nominet"):
            integrity.test_uk_nameservers_span_distinct_operators(built)

    def test_uk_tolerates_a_missing_annotations_key(self):
        built = self.built(
            tlds={"uk": tld_entry(tld="uk", nameservers=[])},
            orgs=[
                org(slug="nominet", source_names={"asn": ["A"]}),
                org(slug="ultradns", source_names={"asn": ["B"]}),
            ],
        )

        with pytest.warns(AsnDriftWarning):
            integrity.test_uk_nameservers_span_distinct_operators(built)

    def test_uk_fails_when_the_operator_is_absent_for_another_reason(self):
        built = self.built(
            tlds={"uk": tld_entry(tld="uk", nameservers=[])},
            orgs=[
                org(slug="nominet", source_names={"asn": ["A"]}),
                org(slug="ultradns", source_names={"iana": ["B"]}),
            ],
        )

        with pytest.raises(AssertionError, match="ultradns"):
            integrity.test_uk_nameservers_span_distinct_operators(built)

    def test_knipp_warns_when_its_asn_label_left(self):
        """The realistic graph: knipp keeps a live iana key and loses only its asn one."""
        record = org(
            slug="knipp-medien", source_names={"iana": ["KNIPP"], "asn": ["GONE"]}
        )
        record["roles"] = {"iana": {"tech": ["de"]}}
        built = self.built(
            tlds={"de": tld_entry(tld="de", iana={"tech": "KNIPP"})}, orgs=[record]
        )

        with pytest.warns(AsnDriftWarning, match="knipp"):
            integrity.test_knipp_spans_iana_tech_and_asn_operator(built)

    def test_knipp_fails_when_the_iana_role_is_missing(self):
        record = org(slug="knipp-medien", source_names={"asn": ["GONE"]})

        with pytest.raises(AssertionError, match="iana tech"):
            integrity.test_knipp_spans_iana_tech_and_asn_operator(
                self.built(orgs=[record])
            )

    def test_knipp_fails_when_asn_absence_is_not_drift(self):
        record = org(
            slug="knipp-medien", source_names={"iana": ["KNIPP"], "asn": ["LIVE"]}
        )
        record["roles"] = {"iana": {"tech": ["de"]}}
        built = self.built(
            tlds={
                "de": tld_entry(
                    tld="de",
                    iana={"tech": "KNIPP"},
                    nameservers=[{"ipv4": [{"as_org": "LIVE"}]}],
                )
            },
            orgs=[record],
        )

        with pytest.raises(AssertionError, match="other than asn drift"):
            integrity.test_knipp_spans_iana_tech_and_asn_operator(built)
