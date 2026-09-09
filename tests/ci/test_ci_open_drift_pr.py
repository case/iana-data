"""End-to-end tests for bin/ci-open-drift-pr, driven against scratch repos.

The script runs once a week on a runner and never locally, so every case here
builds a throwaway repo plus a bare remote and stubs `gh` on PATH.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = REPO_ROOT / "bin" / "ci-open-drift-pr"

ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": "/nonexistent",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
}

GH_STUB = """#!/usr/bin/env bash
# Records argv, then answers from GH_STUB_* so a case can pick the branch taken.
printf '%s\\n' "$*" >> "$GH_STUB_LOG"
case "$1 $2" in
  "pr view") [ -n "${GH_STUB_PR_STATE:-}" ] || exit 1; echo "$GH_STUB_PR_STATE" ;;
  "pr create")
    [ "${GH_STUB_CREATE_FAILS:-}" = 1 ] && {
      echo "pull request create failed: GraphQL: GitHub Actions is not permitted" >&2
      exit 1
    }
    echo "https://github.com/o/r/pull/1" ;;
  "pr comment") ;;
  *) exit 1 ;;
esac
"""

# Stands in for bin/fetch-coordinates so no test reaches Wikidata.
REFRESH_STUB = """#!/usr/bin/env bash
[ "${REFRESH_WRITES:-1}" = 1 ] && printf '%s\\n' "${REFRESH_CONTENT:-refreshed}" \
  > data/manual/places.json
exit "${REFRESH_STATUS:-0}"
"""


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=check,
        env=ISOLATED_GIT_ENV,
    )


@pytest.fixture
def workspace(tmp_path):
    """A repo with a bare origin, a stubbed gh and a stubbed bin/fetch-coordinates."""
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(remote)],
        check=True,
        env=ISOLATED_GIT_ENV,
    )

    repo = tmp_path / "repo"
    (repo / "data" / "manual").mkdir(parents=True)
    (repo / "bin").mkdir()
    (repo / "data" / "manual" / "places.json").write_text("original\n")
    fetch = repo / "bin" / "fetch-coordinates"
    fetch.write_text(REFRESH_STUB)
    fetch.chmod(0o755)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")

    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    gh = stub_dir / "gh"
    gh.write_text(GH_STUB)
    gh.chmod(0o755)

    report = tmp_path / "drift-report.log"
    report.write_text(
        "DRIFT miami: 25.78333,-80.21667 -> 25.77417,-80.19361 (0.023 deg)\n"
    )

    return {
        "repo": repo,
        "remote": remote,
        "stub_dir": stub_dir,
        "report": report,
        "outputs": tmp_path / "github-output",
        "gh_log": tmp_path / "gh.log",
        "workdir": tmp_path / "runner-temp",
    }


def run(workspace, **env) -> dict:
    workspace["workdir"].mkdir(exist_ok=True)
    result = subprocess.run(
        [str(SCRIPT), str(workspace["report"])],
        cwd=workspace["repo"],
        capture_output=True,
        text=True,
        check=False,
        env={
            **ISOLATED_GIT_ENV,
            "PATH": f"{workspace['stub_dir']}:{ISOLATED_GIT_ENV['PATH']}",
            "GITHUB_OUTPUT": str(workspace["outputs"]),
            "RUNNER_TEMP": str(workspace["workdir"]),
            "GH_STUB_LOG": str(workspace["gh_log"]),
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "case/iana-data",
            **env,
        },
    )
    outputs = {}
    if workspace["outputs"].exists():
        for line in workspace["outputs"].read_text().splitlines():
            key, _, value = line.partition("=")
            outputs[key] = value
    return {"result": result, "outputs": outputs}


def remote_branches(workspace) -> list[str]:
    out = git(workspace["remote"], "for-each-ref", "--format=%(refname:short)")
    return out.stdout.split()


class TestPrCreation:
    def test_opens_a_pr_and_pushes_the_branch(self, workspace):
        seen = run(workspace)

        assert seen["result"].returncode == 0, seen["result"].stderr
        assert seen["outputs"]["outcome"] == "pr_opened"
        assert seen["outputs"]["pr_url"] == "https://github.com/o/r/pull/1"
        assert "coordinate-drift" in remote_branches(workspace)

    def test_blocked_create_still_pushes_and_reports_a_compare_url(self, workspace):
        """The bug this script was written for: a refused PR must not lose the alert."""
        seen = run(workspace, GH_STUB_CREATE_FAILS="1")

        assert seen["result"].returncode == 0, seen["result"].stderr
        assert seen["outputs"]["outcome"] == "pr_blocked"
        assert seen["outputs"]["compare_url"] == (
            "https://github.com/case/iana-data/compare/coordinate-drift?expand=1"
        )
        assert "coordinate-drift" in remote_branches(workspace)

    def test_open_pr_gets_a_comment_instead_of_a_second_pr(self, workspace):
        seen = run(workspace, GH_STUB_PR_STATE="OPEN")

        assert seen["outputs"]["outcome"] == "pr_updated"
        gh_calls = workspace["gh_log"].read_text()
        assert "pr comment" in gh_calls
        assert "pr create" not in gh_calls


class TestNotificationDeduplication:
    def test_unchanged_content_is_not_announced_again(self, workspace):
        """An unresolved drift must not re-notify every week."""
        first = run(workspace)
        assert first["outputs"]["outcome"] == "pr_opened"
        workspace["outputs"].unlink()

        git(workspace["repo"], "checkout", "-q", "main")
        second = run(workspace, GH_STUB_PR_STATE="OPEN")

        assert second["outputs"]["outcome"] == "unchanged"
        pushed = git(
            workspace["remote"], "show", "coordinate-drift:data/manual/places.json"
        )
        assert pushed.stdout.strip() == "refreshed"

    def test_unrelated_main_commits_do_not_look_like_new_drift(self, workspace):
        """main moves nightly; only data/manual decides whether the drift is new."""
        run(workspace)
        workspace["outputs"].unlink()

        repo = workspace["repo"]
        git(repo, "checkout", "-q", "main")
        (repo / "data" / "unrelated.json").write_text("nightly\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "unrelated nightly update")

        second = run(workspace, GH_STUB_PR_STATE="OPEN")

        assert second["outputs"]["outcome"] == "unchanged"

    def test_the_branch_is_rebased_even_when_the_content_is_unchanged(self, workspace):
        """A stale base conflicts once main edits the same file.

        data/manual ends byte-identical to the branch's, so the subtree key says
        "unchanged" while the base has still moved underneath it.
        """
        run(workspace)
        workspace["outputs"].unlink()

        repo = workspace["repo"]
        git(repo, "checkout", "-q", "main")
        (repo / "data" / "manual" / "places.json").write_text("curator-value\n")
        (repo / "unrelated.txt").write_text("nightly\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "curator edit plus unrelated churn")
        main_tip = git(repo, "rev-parse", "main").stdout.strip()

        # The refresh writes the default content back, so data/manual matches.
        second = run(workspace, GH_STUB_PR_STATE="OPEN")

        assert second["outputs"]["outcome"] == "unchanged"
        parent = git(workspace["remote"], "rev-parse", "coordinate-drift^").stdout
        assert parent.strip() == main_tip, "branch was not rebased onto current main"

    def test_changed_content_pushes_and_reports_new_drift(self, workspace):
        run(workspace)
        workspace["outputs"].unlink()

        git(workspace["repo"], "checkout", "-q", "main")
        second = run(
            workspace, GH_STUB_PR_STATE="OPEN", REFRESH_CONTENT="drifted-again"
        )

        assert second["outputs"]["outcome"] == "pr_updated"
        assert second["result"].returncode == 0, second["result"].stderr
        pushed = git(
            workspace["remote"], "show", "coordinate-drift:data/manual/places.json"
        )
        assert pushed.stdout.strip() == "drifted-again"


class TestRefreshFailure:
    def test_partial_refresh_failure_is_reported_and_still_lands(self, workspace):
        """--refresh exits 1 on an unfetchable place; the rest is still worth landing."""
        seen = run(workspace, REFRESH_STATUS="1")

        assert seen["result"].returncode == 0, seen["result"].stderr
        assert seen["outputs"]["refresh_failed"] == "true"
        assert seen["outputs"]["outcome"] == "pr_opened"
        body = (workspace["workdir"] / "pr-body.md").read_text()
        assert "could not fetch every place" in body

    def test_failed_refresh_that_writes_nothing_is_reported(self, workspace):
        """Drift was found and could not be fixed: the loudest case, and it was silent."""
        seen = run(workspace, REFRESH_STATUS="1", REFRESH_WRITES="0")

        assert seen["result"].returncode == 0, seen["result"].stderr
        assert seen["outputs"]["outcome"] == "refresh_failed"
        assert "coordinate-drift" not in remote_branches(workspace)

    def test_refresh_writing_nothing_is_a_no_op(self, workspace):
        seen = run(workspace, REFRESH_WRITES="0")

        assert seen["result"].returncode == 0
        assert seen["outputs"]["outcome"] == "no_changes"
        assert "coordinate-drift" not in remote_branches(workspace)


def test_pr_body_carries_the_drift_report_and_the_approval_note(workspace):
    run(workspace)

    body = (workspace["workdir"] / "pr-body.md").read_text()
    assert "DRIFT miami" in body
    assert "need manual approval" in body
