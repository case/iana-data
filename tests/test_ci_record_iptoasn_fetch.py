"""Tests for bin/ci-record-iptoasn-fetch.py.

bin/ is not an importable package, so the script is loaded by path, the same way
tests/test_ci_archive_asn_labels.py loads the archiver.

The pairing rule is why this file exists: a run id without a download date names
an artifact that never fed the build, and the nightly decides which pair to pass
from the build mode it actually took.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "bin" / "ci-record-iptoasn-fetch.py"
_spec = importlib.util.spec_from_file_location("ci_record_iptoasn_fetch", _SCRIPT)
assert _spec is not None and _spec.loader is not None
recorder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recorder)

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"


@pytest.fixture
def metadata_file(tmp_path, monkeypatch):
    path = tmp_path / "metadata.json"
    monkeypatch.setattr("src.utilities.metadata.METADATA_FILE", str(path))
    return path


def _run(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["ci-record-iptoasn-fetch", *args])
    return recorder.main()


def test_a_consumed_artifact_records_the_producer_run(metadata_file, monkeypatch):
    assert (
        _run(
            monkeypatch,
            "--consumed",
            "true",
            "--downloaded-at",
            "2026-09-24T03:36:05Z",
            "--run-id",
            "35952113913",
        )
        == 0
    )

    entry = json.loads(metadata_file.read_text())["IPTOASN"]
    assert entry["last_downloaded"] == "2026-09-24T03:36:05Z"
    assert entry["run_id"] == "35952113913"
    assert entry["last_checked"]


def test_a_preserve_night_records_only_last_checked(metadata_file, monkeypatch):
    assert _run(monkeypatch) == 0

    entry = json.loads(metadata_file.read_text())["IPTOASN"]
    assert entry["last_checked"]
    assert "last_downloaded" not in entry
    assert "run_id" not in entry


@pytest.mark.parametrize(
    "args",
    [
        ("--downloaded-at", "2026-09-24T03:36:05Z"),
        ("--run-id", "35952113913"),
    ],
)
def test_the_two_flags_must_be_given_together(metadata_file, monkeypatch, args):
    """Either one alone would record an artifact nobody can trace."""
    with pytest.raises(SystemExit) as exit_info:
        _run(monkeypatch, *args)

    assert exit_info.value.code == 2
    assert not metadata_file.exists()


def test_both_workflows_pass_the_recency_flag():
    """The predicate is inert unless the flag reaches the checker."""
    for name in ("update-data.yaml", "check-asn-drift.yaml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "--artifact-created-at" in text, name
        assert "updated_at" in text, name


def _build_step_branches():
    """The build step's two branches, bounded by its own `fi`."""
    text = (WORKFLOWS / "update-data.yaml").read_text(encoding="utf-8")
    start = text.index("- name: Build tlds.json")
    body = text[start : text.index("\n          fi\n", start)]
    head, sep, tail = body.partition("\n          else\n")
    assert sep, "the build step no longer has the expected if/else shape"
    return head, tail


def test_the_full_build_branch_is_the_one_that_records_a_download():
    head, _ = _build_step_branches()

    assert "./bin/build --all" in head
    assert 'echo "consumed_asn=true"' in head
    assert 'echo "consumed_asn=false"' not in head


def test_the_preserve_branch_records_no_download():
    """A preserve night is iptoasn's 304; the download date must not move."""
    _, tail = _build_step_branches()

    assert "./bin/build --preserve-asn" in tail
    assert 'echo "consumed_asn=false"' in tail
    assert 'echo "consumed_asn=true"' not in tail


def test_neither_assignment_escapes_the_if_block():
    """Moving one past the `fi` satisfied an earlier, unbounded version."""
    text = (WORKFLOWS / "update-data.yaml").read_text(encoding="utf-8")
    start = text.index("- name: Build tlds.json")
    after_fi = text[
        text.index("\n          fi\n", start) : text.index("- name:", start + 10)
    ]

    assert "consumed_asn" not in after_fi


@pytest.mark.parametrize("flag", ["false", "FALSE", "", "yes", "1", "truthy"])
def test_only_the_literal_true_records_a_download(metadata_file, monkeypatch, flag):
    """The branch lives in Python now, so no shell edit can swap it."""
    assert (
        _run(
            monkeypatch,
            "--consumed",
            flag,
            "--downloaded-at",
            "2026-09-24T03:36:05Z",
            "--run-id",
            "35952113913",
        )
        == 0
    )

    entry = json.loads(metadata_file.read_text())["IPTOASN"]
    assert entry["last_checked"]
    assert "last_downloaded" not in entry
    assert "run_id" not in entry


@pytest.mark.parametrize("flag", ["true", "TRUE", " true "])
def test_a_consumed_build_records_the_pair(metadata_file, monkeypatch, flag):
    assert (
        _run(
            monkeypatch,
            "--consumed",
            flag,
            "--downloaded-at",
            "2026-09-24T03:36:05Z",
            "--run-id",
            "35952113913",
        )
        == 0
    )

    entry = json.loads(metadata_file.read_text())["IPTOASN"]
    assert entry["last_downloaded"] == "2026-09-24T03:36:05Z"
    assert entry["run_id"] == "35952113913"


def test_the_record_step_passes_the_build_mode_through():
    """The step must hand --consumed the build's own output, not health."""
    text = (WORKFLOWS / "update-data.yaml").read_text(encoding="utf-8")

    assert '--consumed "$CONSUMED"' in text
    assert "CONSUMED: ${{ steps.build.outputs.consumed_asn }}" in text


def test_both_consumers_refuse_an_ambiguous_artifact_set():
    """merge-multiple is last-writer-wins, so two artifacts hide stale bytes."""
    for name in ("update-data.yaml", "check-asn-drift.yaml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "actions/runs/$RUN_ID/artifacts" in text or (
            "actions/runs/$run_id/artifacts" in text
        ), name
        assert "expected exactly 1" in text, name
