"""End-to-end tests for the CI data-update scripts, driven against scratch repos.

These are the only coverage the signing path has: it runs once a night on a
runner and never locally. Every case here builds a throwaway repo under tmp_path
and drives bin/ci-apply-data-patch and bin/ci-land-data-patch as CI does.
"""

import base64
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
APPLY = REPO_ROOT / "bin" / "ci-apply-data-patch"
LAND = REPO_ROOT / "bin" / "ci-land-data-patch"
MAKE = REPO_ROOT / "bin" / "ci-make-data-patch"

# The scripts write .git/config and sign commits, so the developer's own global
# config must not reach them. /dev/null reads as an empty config file.
ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": "/nonexistent",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
}


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=check,
        env=ISOLATED_GIT_ENV,
    )


def run_script(
    script: Path, repo: Path, *args: str, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(script), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env={**ISOLATED_GIT_ENV, **(env or {})},
    )


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.invalid")
    return path


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", message)


@pytest.fixture
def seeded(tmp_path: Path) -> Path:
    """A repo holding a small data/ tree plus a file the patch must never touch."""
    repo = init_repo(tmp_path / "consumer")
    (repo / "data" / "generated").mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "data" / "generated" / "keep.json").write_text("{}\n")
    (repo / "data" / "generated" / "gone.json").write_text("{}\n")
    (repo / ".github" / "workflows" / "update-data.yaml").write_text("name: nightly\n")
    commit_all(repo, "seed")
    return repo


def make_patch(seeded: Path, tmp_path: Path, build) -> Path:
    """Produce a patch the way update-data does, from a clone of `seeded`."""
    producer = tmp_path / "producer"
    git(tmp_path, "clone", "-q", str(seeded), str(producer))
    git(producer, "config", "user.name", "Test")
    git(producer, "config", "user.email", "test@example.invalid")
    build(producer)
    git(producer, "add", "--intent-to-add", "--", ".")
    patch = tmp_path / "data-update.patch"
    patch.write_text(
        git(producer, "diff", "--no-renames", "--binary", "--full-index", "HEAD").stdout
    )
    return patch


def legitimate_change(producer: Path) -> None:
    (producer / "data" / "generated" / "keep.json").write_text('{"v": 2}\n')
    (producer / "data" / "generated" / "added.json").write_text("{}\n")
    (producer / "data" / "generated" / "gone.json").unlink()


class TestApplyDataPatch:
    def test_accepts_a_data_only_patch_and_stages_every_change(self, seeded, tmp_path):
        patch = make_patch(seeded, tmp_path, legitimate_change)

        result = run_script(APPLY, seeded, str(patch))

        assert result.returncode == 0, result.stdout + result.stderr
        # --no-renames: gone.json and added.json have identical content, so
        # rename detection would otherwise fold the pair into a single R100.
        staged = git(
            seeded, "diff", "--cached", "--no-renames", "--name-status", "HEAD"
        ).stdout.split()
        assert staged == [
            "A",
            "data/generated/added.json",
            "D",
            "data/generated/gone.json",
            "M",
            "data/generated/keep.json",
        ]

    def test_leaves_the_working_tree_untouched(self, seeded, tmp_path):
        """--cached, so a later `uses: ./...` still resolves the checked-out action."""
        patch = make_patch(seeded, tmp_path, legitimate_change)

        assert run_script(APPLY, seeded, str(patch)).returncode == 0

        assert (seeded / "data" / "generated" / "keep.json").read_text() == "{}\n"
        assert not (seeded / "data" / "generated" / "added.json").exists()
        assert (seeded / "data" / "generated" / "gone.json").exists()

    def test_rejects_a_rename_that_carries_a_file_out_of_the_repo_root(
        self, seeded, tmp_path
    ):
        """The bypass found in review: every check sees only a rename's destination."""

        def rename_workflow_into_data(producer: Path) -> None:
            git(
                producer,
                "mv",
                ".github/workflows/update-data.yaml",
                "data/generated/pwned.yaml",
            )

        producer = tmp_path / "producer"
        git(tmp_path, "clone", "-q", str(seeded), str(producer))
        rename_workflow_into_data(producer)
        patch = tmp_path / "evil.patch"
        patch.write_text(
            git(producer, "diff", "--cached", "--binary", "--full-index", "HEAD").stdout
        )
        assert "rename from " in patch.read_text()

        result = run_script(APPLY, seeded, str(patch))

        assert result.returncode == 1
        assert "contains a rename" in result.stdout
        assert (seeded / ".github" / "workflows" / "update-data.yaml").exists()
        assert git(seeded, "diff", "--cached", "--name-only", "HEAD").stdout == ""

    @pytest.mark.parametrize(
        "path,reason",
        [
            (".gitattributes", "repo root"),
            ("src/evil.py", "outside data/"),
            ("data/.gitattributes", "dot segment directly under data/"),
            ("data/generated/.hidden/x.json", "nested dot segment"),
        ],
    )
    def test_rejects_a_path_outside_the_allowlist(self, seeded, tmp_path, path, reason):
        def add_path(producer: Path) -> None:
            target = producer / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x\n")

        patch = make_patch(seeded, tmp_path, add_path)

        result = run_script(APPLY, seeded, str(patch))

        assert result.returncode == 1, f"{reason}: {result.stdout}"
        assert "disallowed path" in result.stdout

    def test_rejects_a_symlink(self, seeded, tmp_path):
        def add_symlink(producer: Path) -> None:
            (producer / "data" / "generated" / "link.json").symlink_to("/etc/passwd")

        patch = make_patch(seeded, tmp_path, add_symlink)

        result = run_script(APPLY, seeded, str(patch))

        assert result.returncode == 1
        assert "non-regular file mode" in result.stdout

    def test_rejects_an_executable_bit(self, seeded, tmp_path):
        def add_executable(producer: Path) -> None:
            script = producer / "data" / "generated" / "run.json"
            script.write_text("{}\n")
            script.chmod(0o755)

        patch = make_patch(seeded, tmp_path, add_executable)

        result = run_script(APPLY, seeded, str(patch))

        assert result.returncode == 1
        assert "non-regular file mode" in result.stdout

    def test_rejects_a_missing_or_empty_patch(self, seeded, tmp_path):
        empty = tmp_path / "empty.patch"
        empty.write_text("")

        assert "missing or empty" in run_script(APPLY, seeded, str(empty)).stdout
        assert (
            "missing or empty"
            in run_script(APPLY, seeded, str(tmp_path / "absent.patch")).stdout
        )

    def test_prints_usage_without_applying_anything(self, seeded):
        result = run_script(APPLY, seeded)

        assert result.returncode == 0
        assert "Usage: bin/ci-apply-data-patch" in result.stdout
        assert git(seeded, "diff", "--cached", "--name-only", "HEAD").stdout == ""


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
def pushable(tmp_path: Path, seeded: Path) -> tuple[Path, Path]:
    """A consumer repo whose origin is a local bare repo it can really push to."""
    bare = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(seeded), str(bare))
    return seeded, bare


GIT_STUB = """#!/usr/bin/env bash
# Records what the real git would have received, then stops the script.
{
  printf 'ARGV\\t%s\\n' "$*"
  printf 'COUNT\\t%s\\n' "${GIT_CONFIG_COUNT:-}"
  printf 'KEY\\t%s\\n' "${GIT_CONFIG_KEY_0:-}"
  printf 'VALUE\\t%s\\n' "${GIT_CONFIG_VALUE_0:-}"
} >> "$GIT_STUB_LOG"
exit 1
"""


def land_env(bare: Path, expected_head: str, key: str, **overrides) -> dict:
    env = {
        "RUNNER_TEMP": str(bare.parent / "runner-temp"),
        "PUSH_REMOTE": str(bare),
        "EXPECTED_HEAD": expected_head,
        "CI_SSH_SIGNING_KEY": key,
        "CI_COMMITTER_NAME": "iana-data bot",
        "CI_COMMITTER_EMAIL": "bot@example.invalid",
    }
    env.update(overrides)
    Path(env["RUNNER_TEMP"]).mkdir(parents=True, exist_ok=True)
    return env


def rebase(repo, bare, key, guards=("data/",), **env_overrides):
    args = [a for g in guards for a in ("--guard", g)]
    return run_script(
        LAND,
        repo,
        "rebase",
        *args,
        env=land_env(
            bare, git(repo, "rev-parse", "HEAD").stdout.strip(), key, **env_overrides
        ),
    )


def land(
    repo,
    bare,
    patch,
    key,
    subject="Update IANA source data files",
    branch="main",
    extra=(),
    guards=("data/",),
    before_commit=None,
    **env_overrides,
):
    """Drive the three CI steps in order: rebase, validate, sign and push."""
    env = land_env(
        bare, git(repo, "rev-parse", "HEAD").stdout.strip(), key, **env_overrides
    )
    guard_args = [a for g in guards for a in ("--guard", g)]
    staged = run_script(LAND, repo, "rebase", *guard_args, env=env)
    if staged.returncode != 0:
        return staged
    applied = run_script(APPLY, repo, str(patch), env=env)
    if applied.returncode != 0:
        return applied
    if before_commit is not None:
        before_commit()
    commit_args = list(extra)
    if "--own" in commit_args:
        commit_args = guard_args + commit_args
    return run_script(
        LAND, repo, "commit", "--subject", subject, *commit_args, branch, env=env
    )


def git_stub(tmp_path: Path) -> tuple[Path, Path]:
    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    stub = stub_dir / "git"
    stub.write_text(GIT_STUB)
    stub.chmod(0o755)
    return stub_dir, tmp_path / "git-stub.log"


def stubbed_rebase(repo, bare, key, stub_dir, log, **env_overrides) -> dict:
    run_script(
        LAND,
        repo,
        "rebase",
        "--guard",
        "data/",
        env=land_env(
            bare,
            "0" * 40,
            key,
            GIT_STUB_LOG=str(log),
            PATH=f"{stub_dir}:{ISOLATED_GIT_ENV['PATH']}",
            **env_overrides,
        ),
    )
    return dict(
        line.split("\t", 1) for line in log.read_text().splitlines() if "\t" in line
    )


def stubbed_land(repo, bare, patch, key, stub_dir, log, **env_overrides) -> dict:
    run_script(
        LAND,
        repo,
        "commit",
        "--guard",
        "data/",
        "--subject",
        "s",
        "main",
        env=land_env(
            bare,
            "0" * 40,
            key,
            GIT_STUB_LOG=str(log),
            PATH=f"{stub_dir}:{ISOLATED_GIT_ENV['PATH']}",
            **env_overrides,
        ),
    )
    return dict(
        line.split("\t", 1) for line in log.read_text().splitlines() if "\t" in line
    )


class TestLandDataPatch:
    def test_applies_signs_and_pushes(self, pushable, tmp_path, signing_key):
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)

        result = land(repo, bare, patch, signing_key)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "gpgsig " in git(repo, "cat-file", "commit", "HEAD").stdout
        assert (
            git(bare, "rev-parse", "main").stdout
            == git(repo, "rev-parse", "HEAD").stdout
        )

    def test_message_lists_changed_files_without_their_prefix(
        self, pushable, tmp_path, signing_key
    ):
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)

        land(repo, bare, patch, signing_key)

        message = git(repo, "log", "-1", "--pretty=%B").stdout
        assert message.startswith("Update IANA source data files\n\nChanged files:\n")
        assert "- added.json\n" in message
        assert "data/generated/" not in message

    def test_the_subject_comes_from_the_caller(self, pushable, tmp_path, signing_key):
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)

        land(
            repo,
            bare,
            patch,
            signing_key,
            subject="Regenerate data from manual curation",
        )

        assert git(repo, "log", "-1", "--pretty=%s").stdout.strip() == (
            "Regenerate data from manual curation"
        )

    def test_removes_the_signing_key_on_success(self, pushable, tmp_path, signing_key):
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        runner_temp = Path(land_env(bare, "x", signing_key)["RUNNER_TEMP"])

        assert land(repo, bare, patch, signing_key).returncode == 0

        assert not (runner_temp / "iana-data-ci-signing").exists()

    def test_removes_the_signing_key_when_signing_fails(
        self, pushable, tmp_path, signing_key
    ):
        """The trap must fire on the failure path too, not only on success."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        runner_temp = Path(land_env(bare, "x", signing_key)["RUNNER_TEMP"])

        result = land(repo, bare, patch, "not-a-key\n")

        assert result.returncode != 0
        assert not (runner_temp / "iana-data-ci-signing").exists()

    @pytest.mark.parametrize(
        "missing",
        [
            "PUSH_REMOTE",
            "RUNNER_TEMP",
            "CI_SSH_SIGNING_KEY",
            "CI_COMMITTER_NAME",
            "CI_COMMITTER_EMAIL",
        ],
    )
    def test_refuses_when_a_required_variable_is_unset(
        self, pushable, tmp_path, signing_key, missing
    ):
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        before = git(bare, "rev-parse", "main").stdout.strip()

        result = land(repo, bare, patch, signing_key, **{missing: ""})

        assert result.returncode == 1
        assert f"{missing} is not configured" in result.stdout
        assert git(bare, "rev-parse", "main").stdout.strip() == before

    @pytest.mark.parametrize(
        "args",
        [
            ("commit", "--guard", "data/", "main"),
            ("commit", "--own", "--subject", "s", "main"),
            ("commit", "--guard", "data/", "--subject", "s"),
            ("rebase", "--guard", "data/", "main"),
            ("sign", "--guard", "data/", "main"),
        ],
        ids=[
            "no-subject",
            "own-without-guard",
            "no-branch",
            "rebase-with-branch",
            "bad-phase",
        ],
    )
    def test_rejects_an_incomplete_invocation(self, pushable, signing_key, args):
        repo, bare = pushable

        result = run_script(LAND, repo, *args, env=land_env(bare, "x", signing_key))

        assert result.returncode == 2

    def test_rejects_a_missing_phase(self, pushable, signing_key):
        """An unexpanded variable in CI would otherwise skip the whole step."""
        repo, bare = pushable

        result = run_script(LAND, repo, env=land_env(bare, "x", signing_key))

        assert result.returncode == 2
        assert "a phase is required" in result.stderr

    def test_help_still_exits_zero(self, pushable, signing_key):
        repo, bare = pushable

        result = run_script(LAND, repo, "--help", env=land_env(bare, "x", signing_key))

        assert result.returncode == 0
        assert "Usage: bin/ci-land-data-patch" in result.stdout

    def test_rejects_an_unknown_option(self, pushable, signing_key):
        repo, bare = pushable

        result = run_script(
            LAND,
            repo,
            "commit",
            "--force",
            "main",
            env=land_env(bare, "x", signing_key),
        )

        assert result.returncode == 2
        assert "unknown option" in result.stderr

    @pytest.mark.parametrize(
        "args",
        [("rebase",), ("rebase", "--subject", "s")],
        ids=["no-guard", "guardless-with-subject"],
    )
    def test_rebase_requires_a_guard(self, pushable, signing_key, args):
        repo, bare = pushable

        result = run_script(LAND, repo, *args, env=land_env(bare, "x", signing_key))

        assert result.returncode == 2
        assert "at least one --guard is required" in result.stderr

    def test_rebase_requires_expected_head(self, pushable, signing_key):
        repo, bare = pushable
        env = land_env(bare, "x", signing_key)
        env["EXPECTED_HEAD"] = ""

        result = run_script(LAND, repo, "rebase", "--guard", "data/", env=env)

        assert result.returncode == 1
        assert "EXPECTED_HEAD is not configured" in result.stdout

    def test_repository_hooks_do_not_run(self, pushable, tmp_path, signing_key):
        """A hook in the checked-out tree is not the CI job's to obey, and a
        pre-commit hook would otherwise see the untrusted patch."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        for name in ("pre-commit", "pre-push"):
            (hooks / name).write_text("#!/usr/bin/env bash\nexit 1\n")
            (hooks / name).chmod(0o755)
        git(repo, "config", "core.hooksPath", str(hooks))

        assert land(repo, bare, patch, signing_key).returncode == 0

    def test_every_guarded_path_is_enforced_not_just_the_first(
        self, pushable, tmp_path, signing_key
    ):
        """--guard is repeatable; a guard that only reads the first is inert."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        clone = tmp_path / "mover"
        git(tmp_path, "clone", "-q", str(bare), str(clone))
        git(clone, "config", "user.name", "Other")
        git(clone, "config", "user.email", "other@example.invalid")
        (clone / "data" / "manual").mkdir(parents=True, exist_ok=True)
        (clone / "data" / "manual" / "places.json").write_text('{"moved": 1}\n')
        commit_all(clone, "move the second guarded path only")
        git(clone, "push", "-q", "origin", "main")

        result = land(
            repo, bare, patch, signing_key, guards=("data/generated", "data/manual")
        )

        assert result.returncode == 1
        assert "built against stale inputs" in result.stdout


class TestPushSafety:
    """Both safeguards are server-side ref checks, so a stub cannot prove them."""

    def _advance_remote(self, tmp_path, bare, branch, name, text) -> str:
        clone = tmp_path / f"advance-{branch}"
        git(tmp_path, "clone", "-q", "--branch", branch, str(bare), str(clone))
        git(clone, "config", "user.name", "Other")
        git(clone, "config", "user.email", "other@example.invalid")
        target = clone / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        commit_all(clone, "concurrent push")
        git(clone, "push", "-q", "origin", branch)
        return git(clone, "rev-parse", "HEAD").stdout.strip()

    def test_main_advancing_after_the_rebase_rejects_the_push(
        self, pushable, tmp_path, signing_key
    ):
        """The nightly has no lease; a non-fast-forward push is its safety net."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        theirs = None

        def race():
            nonlocal theirs
            theirs = self._advance_remote(
                tmp_path, bare, "main", "README.md", "landed first\n"
            )

        result = land(repo, bare, patch, signing_key, before_commit=race)

        assert result.returncode != 0, result.stdout + result.stderr
        assert git(bare, "rev-parse", "main").stdout.strip() == theirs

    def test_a_stale_lease_rejects_the_force_push(
        self, pushable, tmp_path, signing_key
    ):
        """The lease is read before the push; something can land in between."""
        repo, bare = pushable
        (tmp_path / "lease1").mkdir()
        first = make_patch(repo, tmp_path / "lease1", legitimate_change)
        assert (
            land(repo, bare, first, signing_key, branch="drift", extra=("--own",))
        ).returncode == 0

        remote_main = git(bare, "rev-parse", "main").stdout.strip()
        git(repo, "checkout", "-q", "--force", "--detach", remote_main)
        (tmp_path / "lease2").mkdir()
        second = make_patch(
            repo,
            tmp_path / "lease2",
            lambda producer: (producer / "data" / "generated" / "keep.json").write_text(
                '{"second": 1}\n'
            ),
        )

        # A git wrapper that lets the branch move between the lease fetch and the
        # push, which is the only window --force-with-lease protects.
        real_git = shutil.which("git")
        stub_dir = tmp_path / "race-bin"
        stub_dir.mkdir()
        racer = tmp_path / "racer.sh"
        racer.write_text(
            "#!/usr/bin/env bash\n"
            f'cd "{tmp_path}/racer-clone" || exit 0\n'
            "printf '{\"raced\": 1}\\n' > data/generated/keep.json\n"
            f"{real_git} add -A\n"
            f"{real_git} -c core.hooksPath=/dev/null commit -q -m raced\n"
            f"{real_git} push -q origin drift\n"
        )
        racer.chmod(0o755)
        stub = stub_dir / "git"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            'for a in "$@"; do\n'
            '  if [ "$a" = "push" ]; then\n'
            f'    [ -f "{tmp_path}/raced" ] || {{ touch "{tmp_path}/raced"; "{racer}"; }}\n'
            "    break\n"
            "  fi\n"
            "done\n"
            f'exec {real_git} "$@"\n'
        )
        stub.chmod(0o755)
        git(tmp_path, "clone", "-q", "--branch", "drift", str(bare), "racer-clone")
        git(tmp_path / "racer-clone", "config", "user.name", "iana-data bot")
        git(
            tmp_path / "racer-clone",
            "config",
            "user.email",
            "bot@example.invalid",
        )

        result = land(
            repo,
            bare,
            second,
            signing_key,
            branch="drift",
            extra=("--own",),
            PATH=f"{stub_dir}:{ISOLATED_GIT_ENV['PATH']}",
        )

        assert result.returncode != 0, result.stdout + result.stderr
        assert "stale info" in (result.stdout + result.stderr).lower() or (
            "rejected" in (result.stdout + result.stderr).lower()
        ), result.stdout + result.stderr


class TestTimeoutBudgets:
    """A job cap below its step sum cancels, and a cancelled job fires no alert."""

    def test_every_job_cap_exceeds_the_sum_of_its_step_caps(self):
        checked = 0
        for workflow in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yaml")):
            text = workflow.read_text()
            for chunk in re.split(r"\n  (?=[a-z][\w-]*:\n)", text):
                name = chunk.split(":", 1)[0].strip()
                job_cap = re.search(r"^    timeout-minutes: (\d+)", chunk, re.MULTILINE)
                if not job_cap:
                    continue
                cap = int(job_cap.group(1))
                steps = sum(
                    int(m)
                    for m in re.findall(
                        r"^      +timeout-minutes: (\d+)", chunk, re.MULTILINE
                    )
                )
                checked += 1
                assert steps < cap, (
                    f"{workflow.name}:{name} steps sum to {steps}, cap is {cap}"
                )
        assert checked >= 4, f"only {checked} jobs inspected; the guard is vacuous"


class TestOwnership:
    def test_refuses_a_branch_last_committed_by_someone_else(
        self, pushable, tmp_path, signing_key
    ):
        """The drift branch is machine-owned; a curator commit stops the run."""
        repo, bare = pushable
        (tmp_path / "own1").mkdir()
        first = make_patch(repo, tmp_path / "own1", legitimate_change)
        assert (
            land(repo, bare, first, signing_key, branch="drift", extra=("--own",))
        ).returncode == 0

        human = tmp_path / "human"
        git(tmp_path, "clone", "-q", str(bare), str(human))
        git(human, "config", "user.name", "Curator")
        git(human, "config", "user.email", "curator@example.invalid")
        git(human, "checkout", "-q", "drift")
        (human / "data" / "generated" / "keep.json").write_text('{"human": 1}\n')
        commit_all(human, "curator edit")
        git(human, "push", "-q", "origin", "drift")
        theirs = git(human, "rev-parse", "HEAD").stdout.strip()

        remote_main = git(bare, "rev-parse", "main").stdout.strip()
        git(repo, "checkout", "-q", "--force", "--detach", remote_main)
        (tmp_path / "own2").mkdir()
        second = make_patch(
            repo,
            tmp_path / "own2",
            lambda producer: (producer / "data" / "generated" / "keep.json").write_text(
                '{"machine": 1}\n'
            ),
        )
        outputs = tmp_path / "own-outputs"

        result = land(
            repo,
            bare,
            second,
            signing_key,
            branch="drift",
            extra=("--own",),
            GITHUB_OUTPUT=str(outputs),
        )

        assert result.returncode == 1
        assert "refusing to force-push over it" in result.stdout
        assert "outcome=branch_diverged" in outputs.read_text()
        assert git(bare, "rev-parse", "drift").stdout.strip() == theirs


class TestLease:
    def test_the_push_carries_a_lease_naming_the_observed_sha(
        self, pushable, tmp_path, signing_key
    ):
        """A bare --force would satisfy every other assertion in this file."""
        repo, bare = pushable

        # First land creates the branch, so its tip is committed by the CI
        # identity and the ownership check passes on the second.
        (tmp_path / "first").mkdir()
        first = make_patch(repo, tmp_path / "first", legitimate_change)
        assert (
            land(repo, bare, first, signing_key, branch="drift", extra=("--own",))
        ).returncode == 0
        observed = git(bare, "rev-parse", "drift").stdout.strip()

        remote_main = git(bare, "rev-parse", "main").stdout.strip()
        git(repo, "checkout", "-q", "--force", "--detach", remote_main)
        (tmp_path / "second").mkdir()
        # A fresh change: the first land already applied legitimate_change's
        # deletion, so replaying it against this clone would fail.
        second = make_patch(
            repo,
            tmp_path / "second",
            lambda producer: (producer / "data" / "generated" / "keep.json").write_text(
                '{"second": 1}\n'
            ),
        )

        real_git = shutil.which("git")
        stub_dir = tmp_path / "push-stub"
        stub_dir.mkdir()
        log = tmp_path / "push.log"
        stub = stub_dir / "git"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            'for a in "$@"; do\n'
            '  if [ "$a" = "push" ]; then\n'
            '    printf \'PUSH\\t%s\\n\' "$*" >> "$GIT_STUB_LOG"\n'
            "    exit 0\n"
            "  fi\n"
            "done\n"
            f'exec {real_git} "$@"\n'
        )
        stub.chmod(0o755)

        result = land(
            repo,
            bare,
            second,
            signing_key,
            branch="drift",
            extra=("--own",),
            GIT_STUB_LOG=str(log),
            PATH=f"{stub_dir}:{ISOLATED_GIT_ENV['PATH']}",
        )

        assert log.exists(), result.stdout + result.stderr
        pushes = [ln for ln in log.read_text().splitlines() if ln.startswith("PUSH\t")]
        assert pushes, log.read_text()
        assert f"--force-with-lease=refs/heads/drift:{observed}" in pushes[-1], pushes[
            -1
        ]


class TestCredentialBoundary:
    """The boundary is the workflow step, not the process.

    Why env -u cannot do it: docs/memory/log/2026-09-09-ci-signing-shared.md
    """

    def _steps_before_signing(self, workflow: str) -> str:
        text = (REPO_ROOT / ".github" / "workflows" / workflow).read_text()
        marker = "CI_SSH_SIGNING_KEY"
        assert marker in text, workflow
        return text[: text.index(marker)]

    @pytest.mark.parametrize("workflow", ["update-data.yaml", "check-coordinates.yaml"])
    def test_the_validator_step_runs_before_any_signing_key(self, workflow):
        before = self._steps_before_signing(workflow)

        assert "bin/ci-apply-data-patch" in before, (
            f"{workflow} validates after the signing key is in scope"
        )
        assert "ci-land-data-patch rebase" in before, workflow

    @pytest.mark.parametrize("workflow", ["update-data.yaml", "check-coordinates.yaml"])
    def test_no_job_level_signing_key(self, workflow):
        """A job-level env would put the key in every step's process."""
        text = (REPO_ROOT / ".github" / "workflows" / workflow).read_text()

        for line in text.splitlines():
            if "CI_SSH_SIGNING_KEY" in line:
                assert line.startswith("          "), (
                    f"{workflow}: signing key is not scoped to a step: {line!r}"
                )

    def test_rebase_runs_without_any_signing_credentials(
        self, pushable, tmp_path, signing_key
    ):
        repo, bare = pushable
        env = land_env(bare, git(repo, "rev-parse", "HEAD").stdout.strip(), signing_key)
        for name in ("CI_SSH_SIGNING_KEY", "CI_COMMITTER_NAME", "CI_COMMITTER_EMAIL"):
            env.pop(name)

        result = run_script(LAND, repo, "rebase", "--guard", "data/", env=env)

        assert result.returncode == 0, result.stdout + result.stderr


class TestMakeDataPatch:
    def test_reports_no_change_and_writes_nothing(self, seeded, tmp_path):
        env = {
            "RUNNER_TEMP": str(tmp_path / "rt"),
            "GITHUB_OUTPUT": str(tmp_path / "out"),
        }
        Path(env["RUNNER_TEMP"]).mkdir(parents=True, exist_ok=True)

        result = run_script(MAKE, seeded, "data/", env=env)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "changed=false" in Path(env["GITHUB_OUTPUT"]).read_text()
        assert not (Path(env["RUNNER_TEMP"]) / "data-update.patch").exists()

    def test_emits_a_patch_and_a_run_scoped_artifact_name(self, seeded, tmp_path):
        (seeded / "data" / "generated" / "new.json").write_text("{}\n")
        env = {
            "RUNNER_TEMP": str(tmp_path / "rt"),
            "GITHUB_OUTPUT": str(tmp_path / "out"),
            "GITHUB_RUN_ID": "77",
            "GITHUB_RUN_ATTEMPT": "2",
        }
        Path(env["RUNNER_TEMP"]).mkdir(parents=True, exist_ok=True)

        result = run_script(MAKE, seeded, "data/", env=env)

        assert result.returncode == 0, result.stdout + result.stderr
        out = Path(env["GITHUB_OUTPUT"]).read_text()
        assert "changed=true" in out
        assert "artifact=data-update-77-2" in out
        assert (Path(env["RUNNER_TEMP"]) / "data-update.patch").stat().st_size > 0

    def test_requires_a_path(self, seeded, tmp_path):
        env = {"RUNNER_TEMP": str(tmp_path / "rt")}
        Path(env["RUNNER_TEMP"]).mkdir(parents=True, exist_ok=True)

        result = run_script(MAKE, seeded, env=env)

        assert result.returncode == 2
        assert "at least one path is required" in result.stderr


class TestRebaseGuard:
    """A patch is built minutes before it lands, and main moves in between."""

    def advance(self, pushable, tmp_path, path: str, text: str) -> str:
        _, bare = pushable
        clone = tmp_path / "other"
        git(tmp_path, "clone", "-q", str(bare), str(clone))
        git(clone, "config", "user.name", "Other")
        git(clone, "config", "user.email", "other@example.invalid")
        target = clone / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        commit_all(clone, "concurrent change")
        git(clone, "push", "-q", "origin", "main")
        return git(clone, "rev-parse", "HEAD").stdout.strip()

    def test_an_unrelated_commit_rebases_instead_of_failing(
        self, pushable, tmp_path, signing_key
    ):
        """The bug this replaced: any commit at all aborted the nightly."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        tip = self.advance(pushable, tmp_path, "README.md", "docs\n")

        result = land(repo, bare, patch, signing_key)

        assert result.returncode == 0, result.stdout + result.stderr
        assert git(repo, "rev-parse", "HEAD^").stdout.strip() == tip
        assert (repo / "README.md").read_text() == "docs\n"

    def test_refuses_when_a_guarded_path_moved(self, pushable, tmp_path, signing_key):
        """The moved file is one the patch never touches: the guard covers the
        flow's generation inputs, not just the paths it writes."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        tip = self.advance(
            pushable, tmp_path, "data/generated/unrelated.json", '{"curated": 1}\n'
        )

        result = land(repo, bare, patch, signing_key)

        assert result.returncode == 1
        assert "built against stale inputs" in result.stdout
        assert git(bare, "rev-parse", "main").stdout.strip() == tip

    def test_refuses_when_ci_code_moved(self, pushable, tmp_path, signing_key):
        """Checking out over bin/ swaps the script bash is still reading."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        tip = self.advance(pushable, tmp_path, "bin/ci-land-data-patch", "#!/bin/sh\n")

        result = land(repo, bare, patch, signing_key)

        assert result.returncode == 1
        assert "changed CI code during the run" in result.stdout
        assert git(bare, "rev-parse", "main").stdout.strip() == tip

    def test_refuses_when_a_workflow_moved(self, pushable, tmp_path, signing_key):
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        self.advance(
            pushable, tmp_path, ".github/workflows/update-data.yaml", "name: x\n"
        )

        result = land(repo, bare, patch, signing_key)

        assert result.returncode == 1
        assert "changed CI code during the run" in result.stdout


class TestCredentialHandling:
    def test_token_never_reaches_git_argv(self, pushable, tmp_path, signing_key):
        """A credential in the remote URL would be world readable via /proc."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        stub_dir, log = git_stub(tmp_path)
        token = "ghs_TOKEN_MUST_NOT_APPEAR_IN_ARGV"

        seen = stubbed_land(
            repo, bare, patch, signing_key, stub_dir, log, GH_TOKEN=token
        )

        assert token not in seen["ARGV"], seen["ARGV"]
        assert "x-access-token" not in seen["ARGV"]

    def test_basic_credential_has_no_trailing_newline(
        self, pushable, tmp_path, signing_key
    ):
        """`base64 <<< ...` appends a newline, which makes the push 401."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        stub_dir, log = git_stub(tmp_path)
        token = "ghs_EXACTLY_THIS"

        seen = stubbed_land(
            repo, bare, patch, signing_key, stub_dir, log, GH_TOKEN=token
        )

        assert seen["COUNT"] == "1"
        # An unscoped key authenticates nothing and the push 401s.
        assert seen["KEY"] == f"http.{bare}.extraheader"
        scheme, encoded = seen["VALUE"].rsplit(" ", 1)
        assert scheme == "Authorization: Basic"
        assert base64.b64decode(encoded) == f"x-access-token:{token}".encode()

    def test_the_rebase_phase_keeps_the_token_out_of_argv(
        self, pushable, tmp_path, signing_key
    ):
        """rebase fetches too, so it configures credentials the same way."""
        repo, bare = pushable
        stub_dir, log = git_stub(tmp_path)
        token = "ghs_TOKEN_MUST_NOT_APPEAR_IN_ARGV"

        seen = stubbed_rebase(repo, bare, signing_key, stub_dir, log, GH_TOKEN=token)

        assert token not in seen["ARGV"], seen["ARGV"]
        assert "x-access-token" not in seen["ARGV"]
        assert seen["COUNT"] == "1"
        assert seen["KEY"] == f"http.{bare}.extraheader"
        scheme, encoded = seen["VALUE"].rsplit(" ", 1)
        assert scheme == "Authorization: Basic"
        assert base64.b64decode(encoded) == f"x-access-token:{token}".encode()

    def test_no_auth_config_when_the_token_is_absent(
        self, pushable, tmp_path, signing_key
    ):
        """The bare-remote path must not inject an empty credential."""
        repo, bare = pushable
        patch = make_patch(repo, tmp_path, legitimate_change)
        stub_dir, log = git_stub(tmp_path)

        seen = stubbed_land(repo, bare, patch, signing_key, stub_dir, log)

        assert seen["COUNT"] == ""
        assert seen["VALUE"] == ""


def test_no_ci_script_is_excluded_from_a_fresh_clone():
    """A gitignored helper passes lint and tests locally, then breaks every run.

    Why bin/lib/ci-git-auth.sh escaped: docs/memory/log/2026-09-09-ci-signing-shared.md
    """
    scripts = sorted(p for p in (REPO_ROOT / "bin").rglob("ci-*") if p.is_file())
    assert len(scripts) >= 5, f"expected the bin/ci-* family, found {scripts}"

    # --no-index, or a rule stops being reported the moment the file is tracked,
    # and this guard passes for the rest of the repository's life.
    result = subprocess.run(
        [
            "git",
            "-C",
            str(REPO_ROOT),
            "check-ignore",
            "--no-index",
            "--verbose",
            "--non-matching",
            *(str(s) for s in scripts),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    ignored = [
        line for line in result.stdout.splitlines() if not line.startswith("::\t")
    ]
    assert not ignored, f"gitignored CI scripts: {ignored}"


def test_the_ignore_guard_catches_the_packaging_defect_it_was_written_for(tmp_path):
    """Red-green: the guard must fail against the layout that shipped broken."""
    repo = init_repo(tmp_path / "regression")
    (repo / ".gitignore").write_text("lib/\n")
    (repo / "bin" / "lib").mkdir(parents=True)
    helper = repo / "bin" / "lib" / "ci-git-auth.sh"
    helper.write_text("#!/usr/bin/env bash\n")

    result = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--no-index", str(helper)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, "the unanchored lib/ rule no longer hides it"
    assert list((repo / "bin").rglob("ci-*")) == [helper], (
        "rglob must reach a nested helper; plain glob was the original blind spot"
    )
