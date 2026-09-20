"""Tests for bin/ci-archive-asn-labels.py.

bin/ is not an importable package, so the script is loaded by path, the same way
tests/test_check_asn_drift.py loads the detector.

The date cases are the reason this file exists: each run rebuilds from main,
which holds no pending entry, so a regenerated archived_on would make an
unchanged proposal differ every night. They span two UTC dates deliberately - a
same-day rerun cannot tell a carried date from a regenerated one.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "bin" / "ci-archive-asn-labels.py"
_spec = importlib.util.spec_from_file_location("ci_archive_asn_labels", _SCRIPT)
assert _spec is not None and _spec.loader is not None
archiver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(archiver)

ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": "/nonexistent",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
}


def _org(slug="verisign", asn=None, archived=None):
    record = {
        "display_name": slug.title(),
        "slug": slug,
        "source_names": {"asn": list(asn)} if asn is not None else {},
        "aliases": [],
    }
    if archived is not None:
        record["archived"] = {"asn": [dict(entry) for entry in archived]}
    return record


def _archived(org):
    return {e["name"]: e["archived_on"] for e in org.get("archived", {}).get("asn", [])}


# --- report parsing -------------------------------------------------------


SUMMARY = "asn check: 3 drifted label(s), artifact healthy\n"


def test_parse_drift_report_groups_by_slug():
    report = (
        "DRIFT verisign VRSN-AC28\nDRIFT verisign HGTLD\n"
        "DRIFT ultradns SECURITYSERVICES\n" + SUMMARY
    )
    assert archiver.parse_drift_report(report) == {
        "verisign": {"VRSN-AC28", "HGTLD"},
        "ultradns": {"SECURITYSERVICES"},
    }


def test_parse_drift_report_keeps_labels_containing_spaces():
    """iptoasn labels carry descriptions, so a naive split loses everything after the first word."""
    report = (
        "DRIFT teleinfo CAICTNET Chinese Academy of Telecommunication Research\n"
        + SUMMARY
    )
    assert archiver.parse_drift_report(report) == {
        "teleinfo": {"CAICTNET Chinese Academy of Telecommunication Research"}
    }


def test_parse_drift_report_ignores_other_lines():
    report = "RETURNED verisign HGTLD\nDRIFT verisign VRSN-AC28\n" + SUMMARY
    assert archiver.parse_drift_report(report) == {"verisign": {"VRSN-AC28"}}


def test_parse_drift_report_rejects_a_malformed_line():
    with pytest.raises(ValueError):
        archiver.parse_drift_report("DRIFT verisign\n" + SUMMARY)


def test_a_crashed_detector_is_not_read_as_cleared_drift():
    """An unhealthy run resolves nothing, so its empty report must not clear a proposal."""
    unhealthy = "UNHEALTHY corrupt gzip\nasn check: unhealthy artifact, 1 problem(s)\n"
    with pytest.raises(ValueError):
        archiver.parse_drift_report(unhealthy)


def test_a_truncated_report_is_rejected():
    """DRIFT lines with no completion footer mean the detector died mid-report."""
    with pytest.raises(ValueError):
        archiver.parse_drift_report("DRIFT verisign VRSN-AC28\n")


def test_duplicate_seeded_labels_are_all_removed():
    """remove() drops one copy, leaving the seed invalid as 'also a source_name'."""
    orgs = [_org(asn=["OLD", "OLD", "LIVE"])]
    archiver.archive_labels(orgs, {"verisign": {"OLD"}}, {}, "2026-09-17")

    assert orgs[0]["source_names"]["asn"] == ["LIVE"]
    assert [e["name"] for e in orgs[0]["archived"]["asn"]] == ["OLD"]


# --- the move -------------------------------------------------------------


def test_archiving_moves_the_label_and_stamps_today():
    orgs = [_org(asn=["VRSN-AC28", "VRSN-AC50-340"])]
    moved = archiver.archive_labels(orgs, {"verisign": {"VRSN-AC28"}}, {}, "2026-09-17")

    assert moved == 1
    assert orgs[0]["source_names"]["asn"] == ["VRSN-AC50-340"]
    assert _archived(orgs[0]) == {"VRSN-AC28": "2026-09-17"}


def test_an_emptied_asn_bucket_is_dropped_not_left_empty():
    """An empty list asserts nothing yet still reads as a live bucket."""
    orgs = [_org(asn=["SECURITYSERVICES"])]
    archiver.archive_labels(orgs, {"verisign": {"SECURITYSERVICES"}}, {}, "2026-09-17")

    assert "asn" not in orgs[0]["source_names"]


def test_archived_entries_stay_sorted_by_name():
    orgs = [
        _org(
            asn=["ZZZ", "AAA"], archived=[{"name": "MMM", "archived_on": "2026-09-01"}]
        )
    ]
    archiver.archive_labels(orgs, {"verisign": {"ZZZ", "AAA"}}, {}, "2026-09-17")

    assert [e["name"] for e in orgs[0]["archived"]["asn"]] == ["AAA", "MMM", "ZZZ"]


def test_an_existing_archived_on_is_never_rewritten():
    orgs = [_org(asn=["OLD"], archived=[{"name": "OLD", "archived_on": "2026-07-16"}])]
    archiver.archive_labels(orgs, {"verisign": {"OLD"}}, {}, "2026-09-17")

    assert _archived(orgs[0]) == {"OLD": "2026-07-16"}
    assert "asn" not in orgs[0]["source_names"]


def test_an_org_with_no_drift_is_untouched():
    orgs = [_org(slug="other", asn=["KEEP"])]
    before = json.dumps(orgs, sort_keys=True)
    archiver.archive_labels(orgs, {"verisign": {"GONE"}}, {}, "2026-09-17")

    assert json.dumps(orgs, sort_keys=True) == before


# --- pending-date carry-forward, across two UTC dates ---------------------


def test_unchanged_drift_carries_the_pending_date_to_a_later_date():
    """The whole point: day two must reproduce day one's file, byte for byte."""
    day_one = [_org(asn=["GONE", "LIVE"])]
    archiver.archive_labels(day_one, {"verisign": {"GONE"}}, {}, "2026-09-17")

    carried = {("verisign", "GONE"): "2026-09-17"}
    day_two = [_org(asn=["GONE", "LIVE"])]
    archiver.archive_labels(day_two, {"verisign": {"GONE"}}, carried, "2026-09-18")

    assert day_two == day_one
    assert _archived(day_two[0]) == {"GONE": "2026-09-17"}


def test_without_carry_forward_the_date_regenerates_and_the_file_differs():
    """Red half of the pair above: proves the assertion can fail."""
    day_one = [_org(asn=["GONE", "LIVE"])]
    archiver.archive_labels(day_one, {"verisign": {"GONE"}}, {}, "2026-09-17")

    day_two = [_org(asn=["GONE", "LIVE"])]
    archiver.archive_labels(day_two, {"verisign": {"GONE"}}, {}, "2026-09-18")

    assert day_two != day_one


def test_additive_drift_keeps_the_old_date_and_stamps_only_the_new_label():
    """{A} grows to {A,B}: the one case mixing a carried date with a fresh one."""
    orgs = [_org(asn=["A", "B", "LIVE"])]
    carried = {("verisign", "A"): "2026-09-17"}
    moved = archiver.archive_labels(
        orgs, {"verisign": {"A", "B"}}, carried, "2026-09-18"
    )

    assert moved == 2
    assert _archived(orgs[0]) == {"A": "2026-09-17", "B": "2026-09-18"}
    assert orgs[0]["source_names"]["asn"] == ["LIVE"]


def test_a_returned_label_leaves_the_proposal_without_leaving_the_archive():
    """Partial return: B stops drifting, so it is not re-proposed; A is unchanged.

    B starts archived, proving the archive is never emptied by a return.
    """
    orgs = [
        _org(asn=["A", "B"], archived=[{"name": "OLD", "archived_on": "2026-07-16"}])
    ]
    carried = {("verisign", "A"): "2026-09-17"}
    archiver.archive_labels(orgs, {"verisign": {"A"}}, carried, "2026-09-18")

    assert _archived(orgs[0]) == {"A": "2026-09-17", "OLD": "2026-07-16"}
    assert orgs[0]["source_names"]["asn"] == ["B"]
    assert len(orgs[0]["archived"]["asn"]) == 2


def test_complete_return_proposes_nothing_and_keeps_the_archive():
    """Every label returns: no drift, so the archive is untouched."""
    orgs = [_org(asn=["A"], archived=[{"name": "OLD", "archived_on": "2026-07-16"}])]
    moved = archiver.archive_labels(orgs, {}, {}, "2026-09-18")

    assert moved == 0
    assert _archived(orgs[0]) == {"OLD": "2026-07-16"}
    assert orgs[0]["source_names"]["asn"] == ["A"]


def test_the_proposal_replaces_a_with_b():
    """{A} becomes {B}: A returned and B drifted on the same night."""
    orgs = [_org(asn=["B"], archived=[{"name": "A", "archived_on": "2026-09-17"}])]
    archiver.archive_labels(orgs, {"verisign": {"B"}}, {}, "2026-09-18")

    assert _archived(orgs[0]) == {"A": "2026-09-17", "B": "2026-09-18"}
    assert "asn" not in orgs[0]["source_names"]


# --- reading dates off the pending branch ---------------------------------


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env=ISOLATED_GIT_ENV,
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A scratch repo holding a pending branch, so no live repository is touched."""
    root = tmp_path / "repo"
    (root / "data" / "manual").mkdir(parents=True)
    _git(root.parent, "init", "--quiet", "-b", "main", str(root))
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    monkeypatch.chdir(root)
    return root


def _commit_seed(repo, orgs, branch):
    path = repo / "data" / "manual" / "organizations.json"
    path.write_text(json.dumps(orgs, indent=2) + "\n", encoding="utf-8")
    _git(repo, "checkout", "--quiet", "-B", branch)
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", f"seed on {branch}")


def test_pending_dates_are_read_off_the_branch(repo):
    _commit_seed(
        repo,
        [_org(archived=[{"name": "GONE", "archived_on": "2026-09-17"}])],
        "asn-drift",
    )
    _git(repo, "checkout", "--quiet", "-B", "main")

    assert archiver.pending_archived_dates("asn-drift") == {
        ("verisign", "GONE"): "2026-09-17"
    }


def test_an_absent_pending_branch_yields_no_dates(repo):
    """First run: no branch exists, so everything is stamped today rather than failing."""
    _commit_seed(repo, [_org(asn=["LIVE"])], "main")

    assert archiver.pending_archived_dates("asn-drift") == {}


def test_a_corrupt_pending_seed_is_an_error_not_an_absence(repo):
    """Silently restamping every date would make an unchanged proposal look new."""
    path = repo / "data" / "manual" / "organizations.json"
    path.write_text("{not json", encoding="utf-8")
    _git(repo, "checkout", "--quiet", "-B", "asn-drift")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "corrupt")
    _git(repo, "checkout", "--quiet", "-B", "main")

    with pytest.raises(archiver.PendingReadError):
        archiver.pending_archived_dates("asn-drift")


# --- end to end through main(), across two UTC dates ----------------------


def _run_main(monkeypatch, report_path, branch, today):
    monkeypatch.setattr(
        "sys.argv",
        [
            "ci-archive-asn-labels.py",
            str(report_path),
            "--branch",
            branch,
            "--today",
            today,
        ],
    )
    return archiver.main()


def _report(repo, *labels, slug="verisign"):
    path = repo / "report.txt"
    lines = [f"DRIFT {slug} {label}" for label in labels]
    lines.append(f"asn check: {len(labels)} drifted label(s), artifact healthy")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_two_runs_on_different_dates_produce_an_identical_seed(repo, monkeypatch):
    """The end-to-end carry-forward: day two must reproduce day one byte for byte.

    A same-day rerun cannot catch this, so the dates are passed explicitly.
    """
    seed = [_org(asn=["GONE", "LIVE"])]
    _commit_seed(repo, seed, "main")
    report = _report(repo, "GONE")

    assert _run_main(monkeypatch, report, "asn-drift", "2026-09-17") == 0
    day_one = (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    )

    # The proposal lands on the pending branch, as the workflow will push it.
    _git(repo, "checkout", "--quiet", "-B", "asn-drift")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "proposal")
    _git(repo, "checkout", "--quiet", "-B", "main")
    (repo / "data" / "manual" / "organizations.json").write_text(
        json.dumps(seed, indent=2) + "\n", encoding="utf-8"
    )

    assert _run_main(monkeypatch, report, "asn-drift", "2026-09-18") == 0
    day_two = (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    )

    assert day_two == day_one
    assert '"archived_on": "2026-09-17"' in day_two


def test_main_refuses_and_writes_nothing_when_the_pending_seed_is_unreadable(
    repo, monkeypatch
):
    _commit_seed(repo, [_org(asn=["GONE", "LIVE"])], "main")
    before = (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    )
    (repo / "data" / "manual" / "organizations.json").write_text(
        "{bad", encoding="utf-8"
    )
    _git(repo, "checkout", "--quiet", "-B", "asn-drift")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "corrupt")
    _git(repo, "checkout", "--quiet", "-B", "main")
    (repo / "data" / "manual" / "organizations.json").write_text(
        before, encoding="utf-8"
    )

    assert _run_main(monkeypatch, _report(repo, "GONE"), "asn-drift", "2026-09-18") == 2
    assert (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    ) == before


def test_main_rejects_a_crashed_detector_report(repo, monkeypatch):
    _commit_seed(repo, [_org(asn=["GONE", "LIVE"])], "main")
    before = (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    )
    report = repo / "report.txt"
    report.write_text(
        "UNHEALTHY corrupt gzip\nasn check: unhealthy artifact, 1 problem(s)\n"
    )

    assert _run_main(monkeypatch, report, "asn-drift", "2026-09-18") == 2
    assert (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    ) == before


# --- the guards that stop an invalid seed reaching main -------------------
#
# Both are what keep a bad archive out of the nightly's blocking test gate, and
# a mutation audit found neither was covered: deleting either guard left every
# test green.


def _org_named(display_name, slug, asn):
    return {
        "display_name": display_name,
        "slug": slug,
        "source_names": {"asn": list(asn)},
        "aliases": [],
    }


def test_a_bad_carried_date_is_refused_even_when_resolution_survives(repo, monkeypatch):
    """Resolution can be preserved by display_name while the seed is still invalid.

    The archived entry's malformed date makes archived_names drop it, but the
    label still resolves through display_name, so the resolution guard sees no
    change. Only validate_organizations catches this, and the nightly's own test
    gate runs that validator.
    """
    seed = [_org_named("NICCHILE", "nic-chile", ["NICCHILE"])]
    _commit_seed(repo, seed, "main")
    before = (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    )

    _commit_seed(
        repo,
        [
            {
                **_org_named("NICCHILE", "nic-chile", []),
                "archived": {
                    "asn": [{"name": "NICCHILE", "archived_on": "2026-99-99"}]
                },
            }
        ],
        "asn-drift",
    )
    _git(repo, "checkout", "--quiet", "-B", "main")
    (repo / "data" / "manual" / "organizations.json").write_text(
        before, encoding="utf-8"
    )

    assert (
        _run_main(
            monkeypatch,
            _report(repo, "NICCHILE", slug="nic-chile"),
            "asn-drift",
            "2026-09-19",
        )
        == 2
    )
    assert (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    ) == before


def test_an_archive_that_loses_a_resolution_key_is_refused(repo, monkeypatch):
    """A dropped archive entry stops the label resolving, which is a lost key.

    Distinct from the case above: here nothing else resolves the label, so the
    resolution map really does change and the equality guard is what fires.
    """
    seed = [_org_named("Verisign", "verisign", ["GONE", "LIVE"])]
    _commit_seed(repo, seed, "main")
    before = (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    )

    _commit_seed(
        repo,
        [
            {
                **_org_named("Verisign", "verisign", ["LIVE"]),
                "archived": {"asn": [{"name": "GONE", "archived_on": "not-a-date"}]},
            }
        ],
        "asn-drift",
    )
    _git(repo, "checkout", "--quiet", "-B", "main")
    (repo / "data" / "manual" / "organizations.json").write_text(
        before, encoding="utf-8"
    )

    assert _run_main(monkeypatch, _report(repo, "GONE"), "asn-drift", "2026-09-19") == 2
    assert (repo / "data" / "manual" / "organizations.json").read_text(
        encoding="utf-8"
    ) == before
