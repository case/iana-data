"""End-to-end tests for the coordinate-drift scripts, driven against scratch repos.

The flow runs once a week on a runner and never locally, so every case here
builds a throwaway repo plus a bare remote and stubs `gh` on PATH. It splits over
two jobs, and so do the tests: bin/ci-refresh-coordinates fetches from Wikidata
and holds no credentials, bin/ci-open-drift-pr signs and pushes and holds both.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
REFRESH = REPO_ROOT / "bin" / "ci-refresh-coordinates"
OPEN_PR = REPO_ROOT / "bin" / "ci-open-drift-pr"
CLOSE_PR = REPO_ROOT / "bin" / "ci-close-drift-pr"

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
  "pr view")
    [ "${GH_STUB_VIEW_ERRORS:-}" = 1 ] && { echo "HTTP 503: upstream unavailable" >&2; exit 1; }
    [ -n "${GH_STUB_PR_STATE:-}" ] || { echo "no pull requests found for branch" >&2; exit 1; }
    echo "$GH_STUB_PR_STATE" ;;
  "pr create")
    [ "${GH_STUB_CREATE_FAILS:-}" = 1 ] && {
      echo "pull request create failed: GraphQL: GitHub Actions is not permitted" >&2
      exit 1
    }
    echo "https://github.com/o/r/pull/1" ;;
  "pr comment") ;;
  "pr close") [ "${GH_STUB_CLOSE_FAILS:-}" = 1 ] && exit 1; exit 0 ;;
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


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def signing_key(tmp_path: Path) -> str:
    if shutil.which("ssh-keygen") is None:
        pytest.skip("ssh-keygen not available")
    key = tmp_path / "ci-signing"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "ci", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    return key.read_text()


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
    commit_all(repo, "seed")
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
        "patch": tmp_path / "coordinate-refresh.patch",
    }


def read_outputs(workspace) -> dict:
    outputs = {}
    if workspace["outputs"].exists():
        for line in workspace["outputs"].read_text().splitlines():
            key, _, value = line.partition("=")
            outputs[key] = value
    return outputs


def base_env(workspace, **env) -> dict:
    workspace["workdir"].mkdir(exist_ok=True)
    return {
        **ISOLATED_GIT_ENV,
        "PATH": f"{workspace['stub_dir']}:{ISOLATED_GIT_ENV['PATH']}",
        "GITHUB_OUTPUT": str(workspace["outputs"]),
        "RUNNER_TEMP": str(workspace["workdir"]),
        "GH_STUB_LOG": str(workspace["gh_log"]),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "case/iana-data",
        "PUSH_REMOTE": str(workspace["remote"]),
        **env,
    }


def run_refresh(workspace, **env) -> dict:
    result = subprocess.run(
        [str(REFRESH)],
        cwd=workspace["repo"],
        capture_output=True,
        text=True,
        check=False,
        env=base_env(workspace, **env),
    )
    return {"result": result, "outputs": read_outputs(workspace)}


LAND = REPO_ROOT / "bin" / "ci-land-data-patch"
APPLY = REPO_ROOT / "bin" / "ci-apply-data-patch"


def run_open_pr(workspace, signing_key, patch=None, **env) -> dict:
    """Drive the three CI steps: rebase, validate, then sign and open the PR."""
    repo = workspace["repo"]
    chosen = patch if patch is not None else workspace["patch"]
    base = base_env(
        workspace,
        EXPECTED_HEAD=git(repo, "rev-parse", "HEAD").stdout.strip(),
        CI_SSH_SIGNING_KEY=signing_key,
        CI_COMMITTER_NAME="iana-data bot",
        CI_COMMITTER_EMAIL="bot@example.invalid",
        **env,
    )
    for step in (
        [str(LAND), "rebase", "--guard", "data/manual"],
        [str(APPLY), str(chosen)],
    ):
        done = subprocess.run(
            step, cwd=repo, capture_output=True, text=True, check=False, env=base
        )
        if done.returncode != 0:
            return {"result": done, "outputs": read_outputs(workspace)}
    result = subprocess.run(
        [str(OPEN_PR), str(workspace["report"])],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=base,
    )
    return {"result": result, "outputs": read_outputs(workspace)}


def fresh_checkout(workspace) -> None:
    """Model a runner starting clean: detached at main, nothing in the worktree."""
    repo = workspace["repo"]
    git(repo, "checkout", "-q", "--force", "--detach", "main")
    git(repo, "reset", "-q", "--hard", "HEAD")


def produce(workspace, **env) -> dict:
    """Run the producer job, then reset the worktree the way a fresh runner is."""
    fresh_checkout(workspace)
    produced = run_refresh(workspace, **env)
    if produced["outputs"].get("changed") == "true":
        shutil.copy(produced["outputs"]["patch"], workspace["patch"])
        git(workspace["repo"], "checkout", "-q", "--", "data/manual")
    return produced


def remote_branches(workspace) -> list[str]:
    out = git(workspace["remote"], "for-each-ref", "--format=%(refname:short)")
    return out.stdout.split()


class TestRefreshProducer:
    def test_emits_a_patch_when_the_refresh_moves_a_file(self, workspace):
        seen = run_refresh(workspace)

        assert seen["result"].returncode == 0, seen["result"].stderr
        assert seen["outputs"]["changed"] == "true"
        assert seen["outputs"]["refresh_failed"] == "false"
        assert Path(seen["outputs"]["patch"]).stat().st_size > 0

    def test_refresh_writing_nothing_is_a_no_op(self, workspace):
        seen = run_refresh(workspace, REFRESH_WRITES="0")

        assert seen["result"].returncode == 0
        assert seen["outputs"]["outcome"] == "no_changes"
        assert seen["outputs"]["changed"] == "false"

    def test_failed_refresh_that_writes_nothing_is_reported(self, workspace):
        """Drift was found and could not be fixed: the loudest case, and it was silent."""
        seen = run_refresh(workspace, REFRESH_STATUS="1", REFRESH_WRITES="0")

        assert seen["result"].returncode == 0
        assert seen["outputs"]["outcome"] == "refresh_failed"
        assert seen["outputs"]["changed"] == "false"

    def test_partial_refresh_failure_still_produces_a_patch(self, workspace):
        """--refresh exits 1 on an unfetchable place; the rest is worth landing."""
        seen = run_refresh(workspace, REFRESH_STATUS="1")

        assert seen["result"].returncode == 0
        assert seen["outputs"]["refresh_failed"] == "true"
        assert seen["outputs"]["changed"] == "true"

    def test_rejects_an_unexpected_argument(self, workspace):
        """`?*)` matched anything and exited 0, so a bad call looked like a clean week."""
        result = subprocess.run(
            [str(REFRESH), "--not-a-flag"],
            cwd=workspace["repo"],
            capture_output=True,
            text=True,
            check=False,
            env=base_env(workspace),
        )

        assert result.returncode == 2
        assert "unexpected argument" in result.stderr
        assert not workspace["outputs"].exists()

    def test_the_producer_holds_no_signing_key(self, workspace):
        """The whole reason for the split: this job parses fetched content."""
        run_refresh(workspace)

        assert not (workspace["workdir"] / "iana-data-ci-signing").exists()


class TestPrCreation:
    def test_opens_a_pr_and_pushes_a_signed_branch(self, workspace, signing_key):
        produce(workspace)

        seen = run_open_pr(workspace, signing_key)

        assert seen["result"].returncode == 0, seen["result"].stderr
        assert seen["outputs"]["outcome"] == "pr_opened"
        assert seen["outputs"]["pr_url"] == "https://github.com/o/r/pull/1"
        assert "coordinate-drift" in remote_branches(workspace)
        pushed = git(workspace["remote"], "cat-file", "commit", "coordinate-drift")
        assert "gpgsig " in pushed.stdout

    def test_the_signing_key_does_not_outlive_the_run(self, workspace, signing_key):
        produce(workspace)

        run_open_pr(workspace, signing_key)

        assert not (workspace["workdir"] / "iana-data-ci-signing").exists()

    def test_blocked_create_still_pushes_and_reports_a_compare_url(
        self, workspace, signing_key
    ):
        """The bug this script was written for: a refused PR must not lose the alert."""
        produce(workspace)

        seen = run_open_pr(workspace, signing_key, GH_STUB_CREATE_FAILS="1")

        assert seen["result"].returncode == 0, seen["result"].stderr
        assert seen["outputs"]["outcome"] == "pr_blocked"
        assert seen["outputs"]["compare_url"] == (
            "https://github.com/case/iana-data/compare/coordinate-drift?expand=1"
        )
        assert "coordinate-drift" in remote_branches(workspace)

    def test_open_pr_gets_a_comment_instead_of_a_second_pr(
        self, workspace, signing_key
    ):
        produce(workspace)

        seen = run_open_pr(workspace, signing_key, GH_STUB_PR_STATE="OPEN")

        assert seen["outputs"]["outcome"] == "pr_updated"
        gh_calls = workspace["gh_log"].read_text()
        assert "pr comment" in gh_calls
        assert "pr create" not in gh_calls

    def test_refuses_when_no_patch_was_staged(self, workspace, signing_key):
        """A signing step reached with an empty index would push a signed no-op."""
        fresh_checkout(workspace)
        seen = subprocess.run(
            [str(OPEN_PR), str(workspace["report"])],
            cwd=workspace["repo"],
            capture_output=True,
            text=True,
            check=False,
            env=base_env(
                workspace,
                CI_SSH_SIGNING_KEY=signing_key,
                CI_COMMITTER_NAME="iana-data bot",
                CI_COMMITTER_EMAIL="bot@example.invalid",
            ),
        )

        assert seen.returncode == 1
        assert "Nothing is staged" in seen.stdout
        assert "coordinate-drift" not in remote_branches(workspace)


class TestArguments:
    """Called wrong, this used to print usage and exit 0, which reads as success."""

    def _run(self, workspace, *args):
        return subprocess.run(
            [str(OPEN_PR), *args],
            cwd=workspace["repo"],
            capture_output=True,
            text=True,
            check=False,
            env=base_env(workspace),
        )

    def test_rejects_a_missing_report(self, workspace):
        result = self._run(workspace)

        assert result.returncode == 2
        assert "drift report path is required" in result.stderr

    def test_rejects_an_option_in_place_of_the_report(self, workspace):
        result = self._run(workspace, "--force")

        assert result.returncode == 2
        assert "drift report path is required" in result.stderr

    def test_rejects_extra_arguments(self, workspace):
        result = self._run(workspace, str(workspace["report"]), "extra")

        assert result.returncode == 2
        assert "exactly one argument" in result.stderr

    def test_rejects_a_report_that_does_not_exist(self, workspace):
        """Validated before the commit: otherwise the branch is pushed, then it dies."""
        result = self._run(workspace, str(workspace["repo"] / "absent.log"))

        assert result.returncode == 2
        assert "no drift report at" in result.stderr
        assert "coordinate-drift" not in remote_branches(workspace)

    def test_help_still_exits_zero(self, workspace):
        result = self._run(workspace, "--help")

        assert result.returncode == 0
        assert "Usage: bin/ci-open-drift-pr" in result.stdout


class TestNotificationDeduplication:
    def test_unchanged_content_is_not_announced_again(self, workspace, signing_key):
        """An unresolved drift must not re-notify every week."""
        produce(workspace)
        first = run_open_pr(workspace, signing_key)
        assert first["outputs"]["outcome"] == "pr_opened"
        workspace["outputs"].unlink()

        produce(workspace)
        second = run_open_pr(workspace, signing_key, GH_STUB_PR_STATE="OPEN")

        assert second["outputs"]["outcome"] == "unchanged"
        pushed = git(
            workspace["remote"], "show", "coordinate-drift:data/manual/places.json"
        )
        assert pushed.stdout.strip() == "refreshed"

    def test_unrelated_main_commits_do_not_look_like_new_drift(
        self, workspace, signing_key
    ):
        """main moves nightly; only data/manual decides whether the drift is new."""
        produce(workspace)
        run_open_pr(workspace, signing_key)
        workspace["outputs"].unlink()

        repo = workspace["repo"]
        git(repo, "checkout", "-q", "--force", "main")
        (repo / "data" / "unrelated.json").write_text("nightly\n")
        commit_all(repo, "unrelated nightly update")

        produce(workspace)
        second = run_open_pr(workspace, signing_key, GH_STUB_PR_STATE="OPEN")

        assert second["outputs"]["outcome"] == "unchanged"

    def test_the_branch_is_rebased_even_when_the_content_is_unchanged(
        self, workspace, signing_key
    ):
        """A stale base conflicts once main edits the same file.

        data/manual ends byte-identical to the branch's, so the subtree key says
        unchanged while the base has still moved underneath it.
        """
        produce(workspace)
        run_open_pr(workspace, signing_key)
        workspace["outputs"].unlink()

        repo = workspace["repo"]
        git(repo, "checkout", "-q", "--force", "main")
        (repo / "data" / "manual" / "places.json").write_text("curator-value\n")
        (repo / "unrelated.txt").write_text("nightly\n")
        commit_all(repo, "curator edit plus unrelated churn")
        git(repo, "push", "-q", "origin", "main")
        main_tip = git(repo, "rev-parse", "main").stdout.strip()

        produce(workspace)
        second = run_open_pr(workspace, signing_key, GH_STUB_PR_STATE="OPEN")

        assert second["outputs"]["outcome"] == "unchanged"
        parent = git(workspace["remote"], "rev-parse", "coordinate-drift^").stdout
        assert parent.strip() == main_tip, "branch was not rebased onto current main"

    def test_changed_content_pushes_and_reports_new_drift(self, workspace, signing_key):
        produce(workspace)
        run_open_pr(workspace, signing_key)
        workspace["outputs"].unlink()

        produce(workspace, REFRESH_CONTENT="drifted-again")
        second = run_open_pr(
            workspace, signing_key, GH_STUB_PR_STATE="OPEN", REFRESH_CONTENT="x"
        )

        assert second["outputs"]["outcome"] == "pr_updated"
        assert second["result"].returncode == 0, second["result"].stderr
        pushed = git(
            workspace["remote"], "show", "coordinate-drift:data/manual/places.json"
        )
        assert pushed.stdout.strip() == "drifted-again"

    def test_a_human_commit_on_the_branch_is_not_discarded(
        self, workspace, signing_key
    ):
        """The lease closes what the 2026-09-09 memo listed as an accepted risk."""
        produce(workspace)
        run_open_pr(workspace, signing_key)
        workspace["outputs"].unlink()

        # A curator pushes onto the drift branch between weekly runs.
        other = workspace["repo"].parent / "other"
        git(workspace["repo"].parent, "clone", "-q", str(workspace["remote"]), "other")
        git(other, "config", "user.name", "Curator")
        git(other, "config", "user.email", "curator@example.invalid")
        git(other, "checkout", "-q", "coordinate-drift")
        (other / "data" / "manual" / "places.json").write_text("curated\n")
        theirs = commit_all(other, "curator fixes one place by hand")
        git(other, "push", "-q", "origin", "coordinate-drift")

        produce(workspace, REFRESH_CONTENT="machine-value")
        second = run_open_pr(workspace, signing_key, GH_STUB_PR_STATE="OPEN")

        assert second["result"].returncode != 0
        head = git(workspace["remote"], "rev-parse", "coordinate-drift").stdout.strip()
        assert head == theirs


def test_pr_body_carries_the_drift_report_and_the_approval_note(workspace, signing_key):
    produce(workspace)

    run_open_pr(workspace, signing_key)

    body = (workspace["workdir"] / "pr-body.md").read_text()
    assert "DRIFT miami" in body
    assert "need manual approval" in body


def test_pr_body_flags_a_partial_refresh(workspace, signing_key):
    produce(workspace, REFRESH_STATUS="1")

    run_open_pr(workspace, signing_key, REFRESH_FAILED="true")

    body = (workspace["workdir"] / "pr-body.md").read_text()
    assert "could not fetch every place" in body


class TestPerCallerWording:
    """One script serves every drift check, so the coordinate strings are defaults."""

    def test_the_caller_supplies_title_branch_and_prose(self, workspace, signing_key):
        produce(workspace)

        seen = run_open_pr(
            workspace,
            signing_key,
            DRIFT_BRANCH="asn-drift",
            DRIFT_PR_TITLE="ASN label drift detected",
            DRIFT_COMMIT_SUBJECT="Archive drifted ASN labels",
            DRIFT_PREAMBLE="The nightly check found asn labels no longer present upstream.",
            DRIFT_REVIEW_INSTRUCTIONS="Merge to archive them.",
        )

        assert seen["outputs"]["outcome"] == "pr_opened"
        gh_calls = workspace["gh_log"].read_text()
        assert "ASN label drift detected" in gh_calls
        assert "Coordinate drift detected" not in gh_calls
        assert "asn-drift" in remote_branches(workspace)

        body = (workspace["workdir"] / "pr-body.md").read_text()
        assert "The nightly check found asn labels no longer present upstream." in body
        assert "Merge to archive them." in body
        assert "Wikidata" not in body

    def test_the_coordinate_caller_keeps_its_own_wording(self, workspace, signing_key):
        produce(workspace)

        run_open_pr(workspace, signing_key)

        body = (workspace["workdir"] / "pr-body.md").read_text()
        assert "drifted past the ~1 km tolerance" in body
        assert "merge if Wikidata's value is the better one" in body
        assert "Coordinate drift detected" in workspace["gh_log"].read_text()


class TestUnchangedRunsAreSilent:
    def test_an_unchanged_run_posts_no_comment_at_all(self, workspace, signing_key):
        """The comment ran before new_content was consulted, so it notified nightly.

        Asserts the absence of the call, not just the outcome string: emitting
        'unchanged' while still commenting is the bug this guards.
        """
        produce(workspace)
        run_open_pr(workspace, signing_key)
        workspace["outputs"].unlink()
        workspace["gh_log"].unlink()

        produce(workspace)
        second = run_open_pr(workspace, signing_key, GH_STUB_PR_STATE="OPEN")

        assert second["outputs"]["outcome"] == "unchanged"
        assert "pr comment" not in workspace["gh_log"].read_text()

    def test_changed_content_on_an_open_pr_still_comments(self, workspace, signing_key):
        """The silence must be keyed on content, not on the PR being open."""
        produce(workspace)

        seen = run_open_pr(workspace, signing_key, GH_STUB_PR_STATE="OPEN")

        assert seen["outputs"]["outcome"] == "pr_updated"
        assert "pr comment" in workspace["gh_log"].read_text()

    def test_a_newly_failed_refresh_is_announced_despite_unchanged_files(
        self, workspace, signing_key
    ):
        """Silence is keyed on content, but a partial refresh is news on its own.

        The drift is still there and the branch does not hold the fetched values,
        so suppressing this would hide the loudest case there is.
        """
        produce(workspace)
        run_open_pr(workspace, signing_key)
        workspace["outputs"].unlink()
        workspace["gh_log"].unlink()

        produce(workspace)
        second = run_open_pr(
            workspace, signing_key, GH_STUB_PR_STATE="OPEN", REFRESH_FAILED="true"
        )

        assert second["outputs"]["outcome"] == "pr_updated"
        assert "pr comment" in workspace["gh_log"].read_text()


class TestCloseDriftPr:
    """Drift clearing must close the proposal, or a stale PR stays mergeable.

    Merging a cleared proposal archives labels that came back, so leaving it open
    is not a harmless no-op.
    """

    BOT = "bot@example.invalid"

    def _run_close(self, workspace, branch="asn-drift", **env) -> dict:
        result = subprocess.run(
            [str(CLOSE_PR), branch],
            cwd=workspace["repo"],
            capture_output=True,
            text=True,
            check=False,
            env=base_env(workspace, CI_COMMITTER_EMAIL=self.BOT, **env),
        )
        return {"result": result, "outputs": read_outputs(workspace)}

    def _branch_owned_by(self, workspace, email, branch="asn-drift"):
        repo = workspace["repo"]
        git(repo, "checkout", "-q", "-B", branch)
        (repo / "data" / "manual" / "proposal.txt").write_text("pending\n")
        git(repo, "add", "-A")
        git(
            repo,
            "-c",
            f"user.email={email}",
            "-c",
            "user.name=whoever",
            "commit",
            "-q",
            "-m",
            "proposal",
        )
        git(repo, "checkout", "-q", "main")

    def test_no_open_pr_is_a_silent_no_op(self, workspace):
        self._branch_owned_by(workspace, self.BOT)

        seen = self._run_close(workspace)

        assert seen["result"].returncode == 0
        assert seen["outputs"]["outcome"] == "no_pr"
        assert "pr close" not in workspace["gh_log"].read_text()

    def test_an_owned_proposal_is_closed_and_the_branch_is_left_alone(self, workspace):
        """Closing alone makes the next run silent; deleting has no lease to protect it."""
        self._branch_owned_by(workspace, self.BOT)

        seen = self._run_close(workspace, GH_STUB_PR_STATE="OPEN")

        assert seen["result"].returncode == 0, seen["result"].stderr
        assert seen["outputs"]["outcome"] == "pr_closed"
        gh_calls = workspace["gh_log"].read_text()
        assert "pr close" in gh_calls
        assert "--delete-branch" not in gh_calls

    def test_closing_is_retried_while_the_pr_is_still_open(self, workspace):
        """A failed close must not be a one-shot: the next run still sees OPEN."""
        self._branch_owned_by(workspace, self.BOT)

        first = self._run_close(
            workspace, GH_STUB_PR_STATE="OPEN", GH_STUB_CLOSE_FAILS="1"
        )
        assert first["result"].returncode != 0

        # A failed close emits no outcome at all; the job's if: failure() alert
        # is what covers it, so there may be nothing to clear here.
        workspace["outputs"].unlink(missing_ok=True)
        second = self._run_close(workspace, GH_STUB_PR_STATE="OPEN")

        assert second["outputs"]["outcome"] == "pr_closed"

    def test_a_branch_a_human_took_over_is_left_alone(self, workspace):
        """Closing over a curator's commit would discard it invisibly."""
        self._branch_owned_by(workspace, "curator@example.com")

        seen = self._run_close(workspace, GH_STUB_PR_STATE="OPEN")

        assert seen["result"].returncode == 0
        assert seen["outputs"]["outcome"] == "branch_diverged"
        assert "pr close" not in workspace["gh_log"].read_text()

    def test_an_unreadable_branch_refuses_rather_than_closing(self, workspace):
        """No local ref means ownership is unknown, which is not the same as ours."""
        seen = self._run_close(workspace, GH_STUB_PR_STATE="OPEN")

        assert seen["result"].returncode == 1
        assert seen["outputs"]["outcome"] == "ownership_unknown"
        assert "pr close" not in workspace["gh_log"].read_text()

    def test_it_requires_a_committer_identity(self, workspace):
        self._branch_owned_by(workspace, self.BOT)

        result = subprocess.run(
            [str(CLOSE_PR), "asn-drift"],
            cwd=workspace["repo"],
            capture_output=True,
            text=True,
            check=False,
            env=base_env(workspace, GH_STUB_PR_STATE="OPEN"),
        )

        assert result.returncode == 2


class TestClosedProposals:
    """A closed PR is recreated on purpose; see the note in bin/ci-open-drift-pr.

    Branch content cannot distinguish a rejected proposal from an identical
    unrejected one. Suppressing on it also abandoned a blocked create for good,
    because a failed create leaves the branch matching the next run's proposal.
    Over-announcing is visible and recoverable; the alternative is not.
    """

    def test_a_closed_pr_is_recreated_rather_than_left_closed(
        self, workspace, signing_key
    ):
        produce(workspace)
        run_open_pr(workspace, signing_key)
        workspace["outputs"].unlink()
        workspace["gh_log"].unlink()

        produce(workspace)
        second = run_open_pr(workspace, signing_key, GH_STUB_PR_STATE="CLOSED")

        assert second["outputs"]["outcome"] == "pr_opened"
        assert "pr create" in workspace["gh_log"].read_text()

    def test_a_blocked_create_is_retried_on_the_next_run(self, workspace, signing_key):
        """The regression that reverted the suppression: a blocked create must retry."""
        produce(workspace)
        first = run_open_pr(workspace, signing_key, GH_STUB_CREATE_FAILS="1")
        assert first["outputs"]["outcome"] == "pr_blocked"
        workspace["outputs"].unlink()
        workspace["gh_log"].unlink()

        produce(workspace)
        second = run_open_pr(workspace, signing_key)

        assert second["outputs"]["outcome"] == "pr_opened"
        assert "pr create" in workspace["gh_log"].read_text()


class TestCloseLookupFailures:
    BOT = "bot@example.invalid"

    def test_a_failed_lookup_is_not_read_as_an_absent_pr(self, workspace):
        """Swallowing the failure leaves an obsolete proposal open and silent."""
        result = subprocess.run(
            [str(CLOSE_PR), "asn-drift"],
            cwd=workspace["repo"],
            capture_output=True,
            text=True,
            check=False,
            env=base_env(
                workspace, CI_COMMITTER_EMAIL=self.BOT, GH_STUB_VIEW_ERRORS="1"
            ),
        )

        assert result.returncode == 1
        assert read_outputs(workspace)["outcome"] == "lookup_failed"
