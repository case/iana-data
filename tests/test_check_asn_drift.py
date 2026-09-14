"""Tests for bin/check-asn-drift.py reporting and exit codes.

bin/ is not an importable package, so the script is loaded by path; main() is
guarded by __main__, so importing only adjusts sys.path and pulls helpers.
"""

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

from src.analyze.asn_health import Thresholds
from src.parse.iptoasn import ASNLookup, ASNRecord


def _asn_record(start, end, org, asn=64500):
    return ASNRecord(start_ip=start, end_ip=end, asn=asn, country="US", org=org)


_SCRIPT = Path(__file__).parent.parent / "bin" / "check-asn-drift.py"
_spec = importlib.util.spec_from_file_location("check_asn_drift", _SCRIPT)
assert _spec is not None and _spec.loader is not None
detector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(detector)


def _seed(slug="verisign", asn=None, archived=None):
    record = {
        "slug": slug,
        "display_name": "VeriSign",
        "source_names": {"asn": list(asn or [])},
        "aliases": [],
    }
    if archived:
        record["archived"] = {
            "asn": [{"name": n, "archived_on": "2026-09-12"} for n in archived]
        }
    return [record]


class TestReportDrift:
    def test_a_seeded_label_with_no_raw_match_is_drift(self, monkeypatch, capsys):
        monkeypatch.setattr(
            detector, "parse_organizations_manual", lambda: _seed(asn=["GONE"])
        )

        assert detector.report_drift({"LIVE"}) == 1
        assert "DRIFT verisign GONE" in capsys.readouterr().out

    def test_a_seeded_label_that_matches_is_not_drift(self, monkeypatch, capsys):
        monkeypatch.setattr(
            detector, "parse_organizations_manual", lambda: _seed(asn=["LIVE"])
        )

        assert detector.report_drift({"LIVE"}) == 0
        assert capsys.readouterr().out == ""

    def test_an_archived_label_seen_live_is_reported_not_counted(
        self, monkeypatch, capsys
    ):
        """RETURNED is information; it is not drift and must not set exit 1."""
        monkeypatch.setattr(
            detector,
            "parse_organizations_manual",
            lambda: _seed(asn=["LIVE"], archived=["BACK"]),
        )

        assert detector.report_drift({"LIVE", "BACK"}) == 0
        assert "RETURNED verisign BACK" in capsys.readouterr().out

    def test_an_archived_label_still_absent_is_silent(self, monkeypatch, capsys):
        monkeypatch.setattr(
            detector,
            "parse_organizations_manual",
            lambda: _seed(asn=["LIVE"], archived=["GONE"]),
        )

        assert detector.report_drift({"LIVE"}) == 0
        assert capsys.readouterr().out == ""


class TestCheckHealth:
    def test_a_missing_artifact_is_a_problem_not_a_crash(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            detector, "get_iptoasn_path", lambda: tmp_path / "absent.gz"
        )

        problems, lookup = detector.check_health()

        assert [p for p in problems if "missing" in p]
        assert lookup is None, "an unreadable artifact must not yield an empty table"

    def test_a_corrupt_gzip_is_a_problem_not_a_crash(self, monkeypatch, tmp_path):
        path = tmp_path / "corrupt.gz"
        path.write_bytes(b"this is not gzip data")
        monkeypatch.setattr(detector, "get_iptoasn_path", lambda: path)

        problems, lookup = detector.check_health()

        assert [p for p in problems if "could not be read" in p]
        assert lookup is None

    def test_a_valid_gzip_of_malformed_rows_yields_no_records(self, tmp_path):
        """Zero, not merely below the floor: counting the rows would also pass."""
        path = tmp_path / "rows.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write("only\ttwo\n" * 100)

        _, count = detector.load_artifact(path)

        assert count == 0

    def test_an_empty_org_field_is_not_a_usable_record(self, tmp_path):
        """The build strips the line, so a trailing tab is not a fifth column.

        Parsing it as one lets an artifact of blank labels pass the gate and
        then resolve to nothing in the build.
        """
        path = tmp_path / "blank.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write("1.0.0.0\t1.0.0.255\t64500\tUS\t\n" * 100)

        _, count = detector.load_artifact(path)

        assert count == 0

    def test_invalid_utf8_is_a_problem_not_a_crash(self, monkeypatch, tmp_path):
        path = tmp_path / "bytes.gz"
        path.write_bytes(gzip.compress(b"1.0.0.0\t1.0.0.255\t1\tUS\t\xff\xfe\n"))
        monkeypatch.setattr(detector, "get_iptoasn_path", lambda: path)

        problems, lookup = detector.check_health()

        assert [p for p in problems if "could not be read" in p]
        assert lookup is None


class TestExitCodes:
    """0 clean, 1 drift, 2 error - the contract the workflow branches on."""

    def test_unhealthy_exits_2_without_building(self, monkeypatch, capsys):
        monkeypatch.setattr(
            detector, "check_health", lambda: (["artifact is missing"], None)
        )
        monkeypatch.setattr(
            detector,
            "build_raw_asn_labels",
            lambda: pytest.fail("must not build on unhealthy input"),
        )
        monkeypatch.setattr("sys.argv", ["check-asn-drift"])

        assert detector.main() == detector.ERROR
        assert "UNHEALTHY artifact is missing" in capsys.readouterr().out

    def test_health_only_exits_0_and_emits_the_machine_line(self, monkeypatch, capsys):
        """The nightly parses asn-health:; removing it would break the gate silently."""
        monkeypatch.setattr(detector, "check_health", lambda: ([], object()))
        monkeypatch.setattr(detector, "repairable_damage", lambda _: 0)
        monkeypatch.setattr(
            detector,
            "build_raw_asn_labels",
            lambda: pytest.fail("--health-only must not build"),
        )
        monkeypatch.setattr("sys.argv", ["check-asn-drift", "--health-only"])

        assert detector.main() == detector.CLEAN
        assert "asn-health: healthy=true damaged=false" in capsys.readouterr().out

    def test_health_only_reports_damage_when_repairable(self, monkeypatch, capsys):
        monkeypatch.setattr(detector, "check_health", lambda: ([], object()))
        monkeypatch.setattr(detector, "repairable_damage", lambda _: 4)
        monkeypatch.setattr("sys.argv", ["check-asn-drift", "--health-only"])

        assert detector.main() == detector.CLEAN
        assert "asn-health: healthy=true damaged=true" in capsys.readouterr().out

    def test_an_unhealthy_run_emits_the_machine_line_too(self, monkeypatch, capsys):
        monkeypatch.setattr(detector, "check_health", lambda: (["broken"], None))
        monkeypatch.setattr("sys.argv", ["check-asn-drift", "--health-only"])

        assert detector.main() == detector.ERROR
        assert "asn-health: healthy=false" in capsys.readouterr().out

    def test_drift_exits_1(self, monkeypatch):
        monkeypatch.setattr(detector, "check_health", lambda: ([], object()))
        monkeypatch.setattr(detector, "build_raw_asn_labels", lambda: {"LIVE"})
        monkeypatch.setattr(
            detector, "parse_organizations_manual", lambda: _seed(asn=["GONE"])
        )
        monkeypatch.setattr("sys.argv", ["check-asn-drift"])

        assert detector.main() == detector.DRIFT

    def test_clean_exits_0(self, monkeypatch):
        monkeypatch.setattr(detector, "check_health", lambda: ([], object()))
        monkeypatch.setattr(detector, "build_raw_asn_labels", lambda: {"LIVE"})
        monkeypatch.setattr(
            detector, "parse_organizations_manual", lambda: _seed(asn=["LIVE"])
        )
        monkeypatch.setattr("sys.argv", ["check-asn-drift"])

        assert detector.main() == detector.CLEAN

    def test_a_build_failure_exits_2_not_1(self, monkeypatch, capsys):
        """A failed build must not read as 'no drift found'."""
        monkeypatch.setattr(detector, "check_health", lambda: ([], object()))

        def boom():
            raise RuntimeError("build exploded")

        monkeypatch.setattr(detector, "build_raw_asn_labels", boom)
        monkeypatch.setattr("sys.argv", ["check-asn-drift"])

        assert detector.main() == detector.ERROR
        assert "build failed" in capsys.readouterr().out


class TestRepairableDamage:
    """The recovery trigger must not latch on damage no artifact can repair."""

    def _committed(self, tmp_path, monkeypatch, label, ip="1.0.0.1"):
        path = tmp_path / "tlds.json"
        path.write_text(
            json.dumps(
                {
                    "tlds": [
                        {
                            "tld": "test",
                            "nameservers": [
                                {"ipv4": [{"ip": ip, "as_org": label}], "ipv6": []}
                            ],
                        }
                    ]
                }
            )
        )
        monkeypatch.setattr(detector, "TLDS_OUTPUT_FILE", str(path))

    def test_damage_this_artifact_can_repair_is_counted(self, tmp_path, monkeypatch):
        self._committed(tmp_path, monkeypatch, "Unknown")
        lookup = ASNLookup([_asn_record("1.0.0.0", "1.0.0.255", "REAL-AS")])

        assert detector.repairable_damage(lookup) == 1

    def test_damage_this_artifact_cannot_repair_is_not_counted(
        self, tmp_path, monkeypatch
    ):
        """Otherwise one permanently unroutable address forces --all forever."""
        self._committed(tmp_path, monkeypatch, "Unknown")

        assert detector.repairable_damage(ASNLookup([])) == 0

    def test_a_sentinel_replacement_is_not_a_repair(self, tmp_path, monkeypatch):
        self._committed(tmp_path, monkeypatch, "Unknown")
        lookup = ASNLookup([_asn_record("1.0.0.0", "1.0.0.255", "Not routed")])

        assert detector.repairable_damage(lookup) == 0

    def test_not_routed_is_not_damage(self, tmp_path, monkeypatch):
        """A real iptoasn label; counting it would force --all every night."""
        self._committed(tmp_path, monkeypatch, "Not routed")
        lookup = ASNLookup([_asn_record("1.0.0.0", "1.0.0.255", "REAL-AS")])

        assert detector.repairable_damage(lookup) == 0


VALID_ROWS = (
    "1.0.0.0\t1.0.0.255\t64500\tUS\tALPHA-AS\n"
    "2.0.0.0\t2.0.0.255\t64501\tUS\tBETA-AS\n"
    "2001:db8::\t2001:db8::ffff\t64502\tUS\tGAMMA-AS\n"
)


class TestSharedParserKeepsValidRows:
    """Every other parser test expects zero, so none would catch a total discard."""

    def test_valid_rows_survive_alongside_malformed_ones(self, tmp_path):
        path = tmp_path / "mixed.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(VALID_ROWS)
            handle.write("short\trow\n")
            handle.write("3.0.0.0\tnot-an-ip\t64503\tUS\tBAD-END\n")
            handle.write("4.0.0.0\t4.0.0.255\tnot-a-number\tUS\tBAD-ASN\n")

        lookup, count = detector.load_artifact(path)

        assert count == 3
        assert lookup.lookup("1.0.0.5").org == "ALPHA-AS"
        assert lookup.lookup("2001:db8::5").org == "GAMMA-AS"
        assert lookup.lookup("3.0.0.5") is None

    def test_a_real_build_resolves_what_the_detector_resolves(
        self, tmp_path, monkeypatch
    ):
        """Through build_tlds_json, so disconnecting its artifact loading fails here.

        Ranges span the whole address space deliberately: narrow synthetic rows
        match no real nameserver, so every comparison would be Unknown to Unknown.
        """
        artifact = tmp_path / "ip2asn-combined.tsv.gz"
        with gzip.open(artifact, "wt", encoding="utf-8") as handle:
            handle.write("0.0.0.0\t255.255.255.255\t64500\tUS\tPARITY-V4-AS\n")
            handle.write(
                "::\tffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff\t64501\tUS\tPARITY-V6-AS\n"
            )
        monkeypatch.setattr("src.build.tlds.get_iptoasn_path", lambda: artifact)
        monkeypatch.setattr(
            "src.utilities.metadata.METADATA_FILE", str(tmp_path / "metadata.json")
        )

        from tests.conftest import build_into

        paths = build_into(tmp_path / "out", preserve_asn=False)
        built = json.loads(paths.tlds_json.read_text(encoding="utf-8"))["tlds"]
        detector_lookup, _ = detector.load_artifact(artifact)

        enriched = {"ipv4": 0, "ipv6": 0}
        for entry in built:
            for nameserver in entry.get("nameservers", []):
                for family in ("ipv4", "ipv6"):
                    for address in nameserver.get(family, []):
                        found = detector_lookup.lookup(address["ip"])
                        expected = found.org if found is not None else "Unknown"
                        assert address["as_org"] == expected, address["ip"]
                        if address["as_org"] != "Unknown":
                            enriched[family] += 1

        # Without these the assertion above holds vacuously on Unknown == Unknown.
        assert enriched["ipv4"] > 1000, enriched
        assert enriched["ipv6"] > 1000, enriched

    def test_the_build_resolves_what_the_detector_resolves(self, tmp_path, monkeypatch):
        """Parity against the builder, not another call to the same parser.

        A blank org field passing the gate and vanishing in the build is the
        divergence this guards.
        """
        path = tmp_path / "shared.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(VALID_ROWS)
            handle.write("5.0.0.0\t5.0.0.255\t64504\tUS\t\n")
        monkeypatch.setattr("src.utilities.download.get_iptoasn_path", lambda: path)

        from src.build.tlds import _ip_to_asn_object
        from src.parse.iptoasn import ASNLookup, parse_gzipped_iptoasn

        build_lookup = ASNLookup(parse_gzipped_iptoasn(path))
        detector_lookup, detector_count = detector.load_artifact(path)

        assert detector_count == 3
        for ip in ("1.0.0.5", "5.0.0.5", "2001:db8::5"):
            built = _ip_to_asn_object(ip, build_lookup)
            found = detector_lookup.lookup(ip)
            expected = found.org if found is not None else "Unknown"
            assert built["as_org"] == expected, ip


class TestCheckHealthEndToEnd:
    """The success path, unmocked: the other health tests all mock it away."""

    def _artifact(self, tmp_path, rows):
        path = tmp_path / "artifact.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(rows)
        return path

    def test_a_small_but_valid_artifact_fails_only_on_the_floors(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(
            detector, "get_iptoasn_path", lambda: self._artifact(tmp_path, VALID_ROWS)
        )
        monkeypatch.setattr(
            detector,
            "source_page_addresses",
            lambda _: {"ipv4": ["1.0.0.5"], "ipv6": []},
        )
        monkeypatch.setattr(detector, "committed_addresses", dict)

        problems, lookup = detector.check_health()

        assert lookup is not None, "a readable artifact must yield a lookup"
        assert [p for p in problems if "usable records" in p]
        assert not [p for p in problems if "unrouted" in p]

    def test_a_healthy_artifact_reports_no_problems_at_all(self, monkeypatch, tmp_path):
        """The success path: an always-adds-a-problem bug disables every refresh."""
        rows = "".join(
            f"10.{i // 256}.{i % 256}.0\t10.{i // 256}.{i % 256}.255"
            f"\t{64500 + i}\tUS\tAS-{i}\n"
            for i in range(4100)
        ) + "".join(
            f"2001:db8:{i:x}::\t2001:db8:{i:x}::ffff\t{70000 + i}\tUS\tV6-{i}\n"
            for i in range(3900)
        )
        monkeypatch.setattr(
            detector, "get_iptoasn_path", lambda: self._artifact(tmp_path, rows)
        )
        addresses = {
            "ipv4": [f"10.{i // 256}.{i % 256}.1" for i in range(4100)],
            "ipv6": [f"2001:db8:{i:x}::1" for i in range(3900)],
        }
        monkeypatch.setattr(detector, "source_page_addresses", lambda _: addresses)
        monkeypatch.setattr(detector, "committed_addresses", lambda: addresses)

        problems, lookup = detector.check_health(
            Thresholds(
                min_records=8000, min_addresses_ipv4=4000, min_addresses_ipv6=3800
            )
        )

        assert problems == []
        assert lookup is not None

    def test_the_two_populations_are_reported_separately(self, monkeypatch, tmp_path):
        """A collapsed current population must not hide behind the committed one."""
        monkeypatch.setattr(
            detector, "get_iptoasn_path", lambda: self._artifact(tmp_path, VALID_ROWS)
        )
        monkeypatch.setattr(
            detector, "source_page_addresses", lambda _: {"ipv4": [], "ipv6": []}
        )
        monkeypatch.setattr(
            detector, "committed_addresses", lambda: {"ipv4": ["1.0.0.5"], "ipv6": []}
        )

        problems, _ = detector.check_health()

        assert [p for p in problems if p.startswith("current TLD pages:")]
        assert [p for p in problems if p.startswith("committed graph:")]


class TestBuildErrorReturn:
    def test_the_wrapper_returns_none_on_a_build_error_dict(self, monkeypatch, capsys):
        """build_tlds_json reports write failures by return value, not by raising.

        Mocks the builder, not the wrapper, so deleting the error check fails.
        """
        monkeypatch.setattr(
            "src.build.tlds.build_tlds_json", lambda *a, **k: {"error": "disk full"}
        )

        assert detector.build_raw_asn_labels() is None
        assert "build error: disk full" in capsys.readouterr().out

    def test_a_returned_build_error_exits_2(self, monkeypatch, capsys):
        monkeypatch.setattr(detector, "check_health", lambda: ([], object()))
        monkeypatch.setattr(detector, "build_raw_asn_labels", lambda: None)
        monkeypatch.setattr("sys.argv", ["check-asn-drift"])

        assert detector.main() == detector.ERROR
        assert "build reported an error" in capsys.readouterr().out

    def test_a_damage_crash_exits_2_not_1(self, monkeypatch, capsys):
        """Damage evaluation sits inside main()'s try; moving it out fails here."""
        monkeypatch.setattr(detector, "check_health", lambda _=None: ([], object()))

        def boom(_):
            raise RuntimeError("damage exploded")

        monkeypatch.setattr(detector, "repairable_damage", boom)
        monkeypatch.setattr("sys.argv", ["check-asn-drift", "--health-only"])

        assert detector.main() == detector.ERROR
        out = capsys.readouterr().out
        assert "asn-health: healthy=false" in out
        assert "damage exploded" in out

    def test_a_health_crash_exits_2_not_1(self, monkeypatch, capsys):
        def boom():
            raise RuntimeError("unexpected")

        monkeypatch.setattr(detector, "check_health", boom)
        monkeypatch.setattr("sys.argv", ["check-asn-drift", "--health-only"])

        assert detector.main() == detector.ERROR
        assert "asn-health: healthy=false" in capsys.readouterr().out


class TestRecoveryDoesNotOscillate:
    """A refresh that breaks as much as it repairs must not trigger itself."""

    def _committed(self, tmp_path, monkeypatch, addresses):
        path = tmp_path / "tlds.json"
        path.write_text(
            json.dumps(
                {
                    "tlds": [
                        {
                            "tld": "test",
                            "nameservers": [
                                {
                                    "ipv4": [
                                        {"ip": ip, "as_org": org}
                                        for ip, org in addresses
                                    ],
                                    "ipv6": [],
                                }
                            ],
                        }
                    ]
                }
            )
        )
        monkeypatch.setattr(detector, "TLDS_OUTPUT_FILE", str(path))

    def test_a_refresh_that_breaks_as_much_as_it_repairs_scores_zero(
        self, tmp_path, monkeypatch
    ):
        """Artifact X repairs A and loses B; without netting this alternates forever."""
        self._committed(
            tmp_path, monkeypatch, [("1.0.0.1", "Unknown"), ("2.0.0.1", "BETA-AS")]
        )
        lookup = ASNLookup([_asn_record("1.0.0.0", "1.0.0.255", "ALPHA-AS")])

        assert detector.repairable_damage(lookup) == 0

    def test_a_net_repair_still_triggers(self, tmp_path, monkeypatch):
        self._committed(
            tmp_path, monkeypatch, [("1.0.0.1", "Unknown"), ("1.0.0.2", "Unknown")]
        )
        lookup = ASNLookup([_asn_record("1.0.0.0", "1.0.0.255", "ALPHA-AS")])

        assert detector.repairable_damage(lookup) == 2

    def test_unreadable_committed_json_is_not_damage(self, tmp_path, monkeypatch):
        path = tmp_path / "tlds.json"
        path.write_text("{not json")
        monkeypatch.setattr(detector, "TLDS_OUTPUT_FILE", str(path))

        assert detector.repairable_damage(ASNLookup([])) == 0


class TestRecoveryCountsDistinctAddresses:
    """One address serves up to 125 nameservers; appearances must not be weighted."""

    def _committed(self, tmp_path, monkeypatch, nameservers):
        path = tmp_path / "tlds.json"
        path.write_text(
            json.dumps(
                {
                    "tlds": [
                        {
                            "tld": "test",
                            "nameservers": [
                                {"ipv4": [dict(a) for a in ns], "ipv6": []}
                                for ns in nameservers
                            ],
                        }
                    ]
                }
            )
        )
        monkeypatch.setattr(detector, "TLDS_OUTPUT_FILE", str(path))

    def test_a_repeated_broken_address_does_not_outvote_two_repairs(
        self, tmp_path, monkeypatch
    ):
        broken = [{"ip": "9.0.0.1", "as_org": "OLD-AS"}]
        self._committed(
            tmp_path,
            monkeypatch,
            [
                [
                    {"ip": "1.0.0.1", "as_org": "Unknown"},
                    {"ip": "1.0.0.2", "as_org": "Unknown"},
                ],
                broken,
                broken,
                broken,
            ],
        )
        lookup = ASNLookup([_asn_record("1.0.0.0", "1.0.0.255", "ALPHA-AS")])

        assert detector.repairable_damage(lookup) == 1

    def test_a_repeated_repair_does_not_outvote_two_breaks(self, tmp_path, monkeypatch):
        repair = [{"ip": "1.0.0.1", "as_org": "Unknown"}]
        self._committed(
            tmp_path,
            monkeypatch,
            [
                repair,
                repair,
                repair,
                [
                    {"ip": "8.0.0.1", "as_org": "OLD-AS"},
                    {"ip": "9.0.0.1", "as_org": "OLD-AS"},
                ],
            ],
        )
        lookup = ASNLookup([_asn_record("1.0.0.0", "1.0.0.255", "ALPHA-AS")])

        assert detector.repairable_damage(lookup) == 0

    def test_an_address_without_an_ip_key_is_skipped_not_raised(
        self, tmp_path, monkeypatch
    ):
        self._committed(tmp_path, monkeypatch, [[{"as_org": "Unknown"}]])

        assert detector.repairable_damage(ASNLookup([])) == 0
