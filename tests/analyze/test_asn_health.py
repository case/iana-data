"""Tests for the iptoasn health signals that pick the nightly's build mode.

Each class names the attack it defends. The measured baseline these thresholds
sit outside: docs/plans/current/2026-09-11-asn-drift-automation.md
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.analyze.asn_health import (
    FAMILIES,
    SENTINEL_LABELS,
    FamilyHealth,
    Thresholds,
    artifact_age_problem,
    health_problems,
    is_useful_label,
    measure,
    nameserver_addresses,
    source_page_addresses,
)
from src.parse.iptoasn import ASNLookup, ASNRecord

HEALTHY_RECORDS = 600_000


def _record(start, end, asn=64500, org="EXAMPLE-AS"):
    return ASNRecord(start_ip=start, end_ip=end, asn=asn, country="US", org=org)


def _lookup(*records):
    return ASNLookup(list(records))


def _addresses(v4=4200, v6=4000):
    """Address sets comfortably above the floors, so a test varies one thing."""
    return {
        "ipv4": [f"10.{i // 256}.{i % 256}.1" for i in range(v4)],
        "ipv6": [f"2001:db8::{i:x}" for i in range(v6)],
    }


def _covering_lookup(org="EXAMPLE-AS", asn=64500):
    return _lookup(
        _record("10.0.0.0", "10.255.255.255", asn=asn, org=org),
        _record("2001:db8::", "2001:db8::ffff", asn=asn, org=org),
    )


def _healthy():
    return measure(_addresses(), _covering_lookup())


def test_a_healthy_artifact_reports_no_problems():
    assert health_problems(_healthy(), HEALTHY_RECORDS) == []


def test_thresholds_match_the_plan():
    """Pinned, because the gate's whole value is these numbers."""
    limits = Thresholds()

    assert (limits.max_unrouted_ipv4, limits.max_unrouted_ipv6) == (25, 60)
    assert limits.min_useful_label_coverage == 0.95
    assert (limits.min_addresses_ipv4, limits.min_addresses_ipv6) == (4000, 3800)
    assert limits.min_records == 500_000


class TestZeroDenominator:
    """0/0 reading as 100% is the guard that fails open if unhandled."""

    def test_an_empty_family_is_a_problem_not_full_coverage(self):
        families = measure({"ipv4": [], "ipv6": []}, _covering_lookup())

        problems = health_problems(families, HEALTHY_RECORDS)

        assert [p for p in problems if "ipv4: no addresses" in p]
        assert [p for p in problems if "ipv6: no addresses" in p]

    def test_an_empty_family_reports_zero_coverage_not_one(self):
        assert FamilyHealth("ipv4", 0, 0, 0).useful_label_coverage == 0.0

    def test_a_missing_family_is_a_problem(self):
        families = {"ipv4": _healthy()["ipv4"]}

        assert [p for p in health_problems(families, HEALTHY_RECORDS) if "ipv6" in p]


class TestUnroutedCeiling:
    """An absent or corrupt artifact resolves nothing, so every address is unrouted."""

    def test_nothing_resolves_is_caught(self):
        families = measure(_addresses(), _lookup())

        problems = health_problems(families, HEALTHY_RECORDS)

        assert [p for p in problems if "unrouted" in p and "ipv4" in p]
        assert [p for p in problems if "unrouted" in p and "ipv6" in p]

    def test_an_asn_zero_record_counts_as_unrouted(self):
        """iptoasn's own not-routed marker, which still carries a label."""
        families = measure(_addresses(), _covering_lookup(org="Not routed", asn=0))

        assert [
            p for p in health_problems(families, HEALTHY_RECORDS) if "unrouted" in p
        ]

    def test_a_few_unrouted_addresses_stay_healthy(self):
        """Observed baseline is 1-2 v4 and 8-10 v6; the ceiling must clear those."""
        lookup = _lookup(
            _record("10.0.0.0", "10.255.255.255"),
            _record("2001:db8::", "2001:db8::ffff"),
        )
        addresses = _addresses()
        addresses["ipv4"] += ["192.0.2.1", "192.0.2.2"]
        addresses["ipv6"] += [f"2001:db8:1::{i:x}" for i in range(10)]

        assert health_problems(measure(addresses, lookup), HEALTHY_RECORDS) == []


class TestUsefulLabelCoverage:
    """The attack cardinality misses: labels replaced while ASNs stay valid."""

    def test_a_sentinel_label_on_a_routed_record_is_caught(self):
        families = measure(_addresses(), _covering_lookup(org="Unknown"))

        problems = health_problems(families, HEALTHY_RECORDS)

        assert [p for p in problems if "useful label" in p]

    def test_it_is_independent_of_the_unrouted_signal(self):
        """asn != 0 with a sentinel label passes the unrouted check and fails this."""
        families = measure(_addresses(), _covering_lookup(org="Unknown", asn=64500))

        problems = health_problems(families, HEALTHY_RECORDS)

        assert not [p for p in problems if "unrouted" in p]
        assert [p for p in problems if "useful label" in p]

    @pytest.mark.parametrize("label", sorted(SENTINEL_LABELS))
    def test_every_sentinel_label_counts_as_useless(self, label):
        families = measure(_addresses(), _covering_lookup(org=label))

        assert [p for p in health_problems(families, HEALTHY_RECORDS) if "useful" in p]


class TestAddressFloor:
    """A collection failure shrinks the population rather than the coverage."""

    def test_a_collapsed_family_is_caught(self):
        families = measure(_addresses(v4=100, v6=100), _covering_lookup())

        problems = health_problems(families, HEALTHY_RECORDS)

        assert [p for p in problems if "ipv4: 100 addresses" in p]
        assert [p for p in problems if "ipv6: 100 addresses" in p]

    def test_one_family_collapsing_alone_is_caught(self):
        families = measure(_addresses(v6=100), _covering_lookup())

        problems = health_problems(families, HEALTHY_RECORDS)

        assert not [p for p in problems if p.startswith("ipv4")]
        assert [p for p in problems if "ipv6: 100 addresses" in p]


class TestRecordFloor:
    """Coverage does not subsume record count: two ranges cover everything."""

    def test_full_coverage_from_two_records_is_still_caught(self):
        families = measure(_addresses(), _covering_lookup())

        assert health_problems(families, record_count=2) == [
            "artifact has 2 usable records, below the 500000 floor"
        ]


class TestMalformedRangesAreDropped:
    """A bad endpoint must not resolve and must not crash the lookup."""

    def test_a_malformed_end_address_does_not_crash_and_does_not_resolve(self):
        lookup = _lookup(_record("10.0.0.0", "not-an-ip"))

        families = measure({"ipv4": ["10.0.0.1"], "ipv6": []}, lookup)

        assert families["ipv4"].unrouted == 1

    def test_a_reversed_range_does_not_shadow_a_valid_one(self):
        """The probe must sit inside the reversed range's shadow.

        Binary search picks the highest start at or below the query, so a
        reversed range masks the valid one underneath unless it is dropped.
        """
        lookup = _lookup(
            _record("10.0.0.0", "10.0.0.255"),
            _record("10.0.0.128", "10.0.0.0"),
        )

        assert (
            measure({"ipv4": ["10.0.0.200"], "ipv6": []}, lookup)["ipv4"].unrouted == 0
        )


class TestNameserverAddresses:
    def test_it_collects_both_families_from_built_entries(self):
        entries = [
            {
                "tld": "test",
                "nameservers": [
                    {"ipv4": [{"ip": "1.1.1.1"}], "ipv6": [{"ip": "2001:db8::1"}]}
                ],
            }
        ]

        assert nameserver_addresses(entries) == {
            "ipv4": ["1.1.1.1"],
            "ipv6": ["2001:db8::1"],
        }

    def test_it_tolerates_entries_without_nameservers(self):
        assert nameserver_addresses([{"tld": "test"}]) == {f: [] for f in FAMILIES}

    def test_measure_deduplicates_repeated_addresses(self):
        """One address on many TLDs is one address, not many."""
        families = measure({"ipv4": ["10.0.0.1"] * 50, "ipv6": []}, _covering_lookup())

        assert families["ipv4"].total == 1


class TestThresholdBoundaries:
    """Inclusivity: the plan says "fails when above 25", so 25 must pass."""

    def test_exactly_the_unrouted_ceiling_passes(self):
        health = FamilyHealth("ipv4", total=4200, unrouted=25, useful_labelled=4200)

        assert (
            health_problems(
                {"ipv4": health, "ipv6": _healthy()["ipv6"]}, HEALTHY_RECORDS
            )
            == []
        )

    def test_one_above_the_unrouted_ceiling_fails(self):
        health = FamilyHealth("ipv4", total=4200, unrouted=26, useful_labelled=4200)

        assert [
            p
            for p in health_problems(
                {"ipv4": health, "ipv6": _healthy()["ipv6"]}, HEALTHY_RECORDS
            )
            if "unrouted" in p
        ]

    def test_exactly_the_address_floor_passes(self):
        health = FamilyHealth("ipv4", total=4000, unrouted=0, useful_labelled=4000)

        assert (
            health_problems(
                {"ipv4": health, "ipv6": _healthy()["ipv6"]}, HEALTHY_RECORDS
            )
            == []
        )

    def test_one_below_the_address_floor_fails(self):
        health = FamilyHealth("ipv4", total=3999, unrouted=0, useful_labelled=3999)

        assert [
            p
            for p in health_problems(
                {"ipv4": health, "ipv6": _healthy()["ipv6"]}, HEALTHY_RECORDS
            )
            if "addresses" in p
        ]

    def test_exactly_the_ipv6_unrouted_ceiling_passes(self):
        health = FamilyHealth("ipv6", total=4000, unrouted=60, useful_labelled=4000)

        assert (
            health_problems(
                {"ipv4": _healthy()["ipv4"], "ipv6": health}, HEALTHY_RECORDS
            )
            == []
        )

    def test_one_above_the_ipv6_unrouted_ceiling_fails(self):
        health = FamilyHealth("ipv6", total=4000, unrouted=61, useful_labelled=4000)

        assert [
            p
            for p in health_problems(
                {"ipv4": _healthy()["ipv4"], "ipv6": health}, HEALTHY_RECORDS
            )
            if "unrouted" in p
        ]

    def test_exactly_the_ipv6_address_floor_passes(self):
        health = FamilyHealth("ipv6", total=3800, unrouted=0, useful_labelled=3800)

        assert (
            health_problems(
                {"ipv4": _healthy()["ipv4"], "ipv6": health}, HEALTHY_RECORDS
            )
            == []
        )

    def test_one_below_the_ipv6_address_floor_fails(self):
        health = FamilyHealth("ipv6", total=3799, unrouted=0, useful_labelled=3799)

        assert [
            p
            for p in health_problems(
                {"ipv4": _healthy()["ipv4"], "ipv6": health}, HEALTHY_RECORDS
            )
            if "addresses" in p
        ]

    def test_exactly_the_useful_label_floor_passes(self):
        """95% of 4000 is 3800 exactly, so the boundary is representable."""
        health = FamilyHealth("ipv4", total=4000, unrouted=0, useful_labelled=3800)

        assert health.useful_label_coverage == 0.95
        assert (
            health_problems(
                {"ipv4": health, "ipv6": _healthy()["ipv6"]}, HEALTHY_RECORDS
            )
            == []
        )

    def test_one_below_the_useful_label_floor_fails(self):
        health = FamilyHealth("ipv4", total=4000, unrouted=0, useful_labelled=3799)

        assert [
            p
            for p in health_problems(
                {"ipv4": health, "ipv6": _healthy()["ipv6"]}, HEALTHY_RECORDS
            )
            if "useful label" in p
        ]

    def test_exactly_the_record_floor_passes(self):
        assert health_problems(_healthy(), record_count=500_000) == []

    def test_one_below_the_record_floor_fails(self):
        assert health_problems(_healthy(), record_count=499_999) != []


class TestUsefulLabelPredicate:
    """An empty label is as useless as a sentinel, and must not count."""

    @pytest.mark.parametrize("label", ["", "   ", None, "Unknown", " Not routed "])
    def test_useless_labels(self, label):
        assert is_useful_label(label) is False

    @pytest.mark.parametrize("label", ["GOOGLE", " GOOGLE ", "AS-AFILIAS1"])
    def test_useful_labels(self, label):
        assert is_useful_label(label) is True

    def test_blank_labels_fail_the_coverage_floor(self):
        families = measure(_addresses(), _covering_lookup(org=""))

        assert [p for p in health_problems(families, HEALTHY_RECORDS) if "useful" in p]


class TestSourcePageAddresses:
    """Pages are sharded into subdirectories; a flat glob finds nothing."""

    def test_it_finds_a_page_in_a_subdirectory(self, tmp_path):
        (tmp_path / "c").mkdir()
        (tmp_path / "c" / "com.html").write_text(
            "<table><tr><th>Name Server</th><th>IP Address</th></tr>"
            "<tr><td>a.example</td><td>1.2.3.4</td></tr></table>",
            encoding="utf-8",
        )

        found = source_page_addresses(tmp_path)

        assert "1.2.3.4" in found["ipv4"]

    def test_an_empty_tree_yields_empty_families(self, tmp_path):
        assert source_page_addresses(tmp_path) == {f: [] for f in FAMILIES}


NOW = datetime(2026, 9, 24, 7, 0, tzinfo=UTC)


def _stamp(**delta):
    """A timestamp `delta` before NOW, in the producer's own RFC3339 shape."""
    return (NOW - timedelta(**delta)).isoformat().replace("+00:00", "Z")


class TestArtifactRecency:
    """A stale artifact reads as healthy, so its labels publish as current."""

    def test_a_fresh_artifact_has_no_problem(self):
        assert artifact_age_problem(_stamp(hours=3), NOW) is None

    def test_zero_age_is_accepted(self):
        assert artifact_age_problem(_stamp(hours=0), NOW) is None

    def test_exactly_the_ceiling_is_accepted(self):
        assert artifact_age_problem(_stamp(hours=40), NOW) is None

    def test_just_over_the_ceiling_is_caught(self):
        problem = artifact_age_problem(_stamp(hours=40, seconds=1), NOW)

        assert problem is not None
        assert "40.00h old" in problem

    def test_yesterdays_artifact_is_accepted_at_the_observed_worst_case(self):
        """37.17h at job start, from the observed producer and nightly offsets."""
        assert artifact_age_problem(_stamp(hours=37, minutes=10), NOW) is None

    def test_yesterdays_artifact_is_accepted_on_a_slow_scrape_night(self):
        """Job start plus the ~2.2h scrape; 0.6h of margin against the ceiling."""
        assert artifact_age_problem(_stamp(hours=39, minutes=24), NOW) is None

    def test_an_artifact_two_cycles_old_is_caught(self):
        """40.73h, the floor for the day-before artifact. An age gate cannot say why."""
        assert artifact_age_problem(_stamp(hours=40, minutes=44), NOW) is not None

    def test_an_empty_timestamp_is_a_problem_not_a_skip(self):
        problem = artifact_age_problem("", NOW)

        assert problem is not None
        assert "empty" in problem

    def test_a_whitespace_timestamp_is_a_problem(self):
        assert artifact_age_problem("   ", NOW) is not None

    def test_an_unparseable_timestamp_is_a_problem(self):
        problem = artifact_age_problem("not-a-date", NOW)

        assert problem is not None
        assert "unparseable" in problem

    def test_a_timezone_naive_timestamp_is_a_problem(self):
        problem = artifact_age_problem("2026-09-24T03:36:05", NOW)

        assert problem is not None
        assert "no timezone" in problem

    def test_a_trailing_z_parses(self):
        assert artifact_age_problem("2026-09-24T04:00:00Z", NOW) is None

    def test_an_offset_timestamp_parses(self):
        assert artifact_age_problem("2026-09-24T05:00:00+02:00", NOW) is None

    def test_clock_skew_inside_the_tolerance_is_accepted(self):
        assert artifact_age_problem(_stamp(minutes=-4), NOW) is None

    def test_a_future_timestamp_beyond_the_tolerance_is_caught(self):
        problem = artifact_age_problem(_stamp(hours=-6), NOW)

        assert problem is not None
        assert "in the future" in problem

    def test_a_far_future_timestamp_cannot_satisfy_the_ceiling(self):
        """A year-2099 stamp passes `age <= ceiling`; only the lower bound stops it."""
        assert artifact_age_problem("2099-01-01T00:00:00Z", NOW) is not None

    def test_the_ceiling_is_overridable(self):
        tight = Thresholds(max_age_hours=6.0)

        assert artifact_age_problem(_stamp(hours=8), NOW, tight) is not None
        assert artifact_age_problem(_stamp(hours=8), NOW) is None

    def test_the_skew_tolerance_is_overridable(self):
        wide = Thresholds(max_clock_skew_minutes=600.0)

        assert artifact_age_problem(_stamp(hours=-6), NOW, wide) is None
