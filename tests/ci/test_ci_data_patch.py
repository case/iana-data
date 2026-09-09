"""End-to-end tests for the CI data-update scripts, driven against scratch repos.

These are the only coverage the signing path has: it runs once a night on a
runner and never locally. Every case here builds a throwaway repo under tmp_path
and drives bin/ci-apply-data-patch and bin/ci-commit-signed-data as CI does.
"""

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
APPLY = REPO_ROOT / "bin" / "ci-apply-data-patch"
COMMIT = REPO_ROOT / "bin" / "ci-commit-signed-data"

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


def commit_env(bare: Path, expected_head: str, key: str, **overrides) -> dict:
    env = {
        "RUNNER_TEMP": str(bare.parent / "runner-temp"),
        "PUSH_REMOTE": str(bare),
        "EXPECTED_HEAD": expected_head,
        "CI_SSH_SIGNING_KEY": key,
        "CI_COMMITTER_NAME": "iana-data bot",
        "CI_COMMITTER_EMAIL": "bot@example.invalid",
        "SOURCE_CHANGED": "true",
    }
    env.update(overrides)
    Path(env["RUNNER_TEMP"]).mkdir(parents=True, exist_ok=True)
    return env


class TestCommitSignedData:
    def test_signs_and_pushes_the_staged_update(self, pushable, tmp_path, signing_key):
        repo, bare = pushable
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        patch = make_patch(repo, tmp_path, legitimate_change)
        assert run_script(APPLY, repo, str(patch)).returncode == 0

        result = run_script(COMMIT, repo, env=commit_env(bare, head, signing_key))

        assert result.returncode == 0, result.stdout + result.stderr
        assert "gpgsig " in git(repo, "cat-file", "commit", "HEAD").stdout
        assert (
            git(bare, "rev-parse", "main").stdout
            == git(repo, "rev-parse", "HEAD").stdout
        )

    def test_commit_message_lists_changed_files_without_their_prefix(
        self, pushable, tmp_path, signing_key
    ):
        repo, bare = pushable
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        patch = make_patch(repo, tmp_path, legitimate_change)
        run_script(APPLY, repo, str(patch))

        run_script(COMMIT, repo, env=commit_env(bare, head, signing_key))

        message = git(repo, "log", "-1", "--pretty=%B").stdout
        assert message.startswith("Update IANA source data files\n\nChanged files:\n")
        assert "- added.json\n" in message
        assert "data/generated/" not in message

    def test_manual_regen_gets_its_own_subject(self, pushable, tmp_path, signing_key):
        repo, bare = pushable
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        patch = make_patch(repo, tmp_path, legitimate_change)
        run_script(APPLY, repo, str(patch))

        run_script(
            COMMIT,
            repo,
            env=commit_env(bare, head, signing_key, SOURCE_CHANGED="false"),
        )

        assert git(repo, "log", "-1", "--pretty=%s").stdout.strip() == (
            "Regenerate data from manual curation"
        )

    def test_refuses_when_main_advanced_during_the_update(
        self, pushable, tmp_path, signing_key
    ):
        repo, bare = pushable
        stale_head = git(repo, "rev-parse", "HEAD").stdout.strip()
        patch = make_patch(repo, tmp_path, legitimate_change)
        run_script(APPLY, repo, str(patch))

        # Someone else pushes to main while the update was being built.
        other = init_repo(tmp_path / "other")
        git(tmp_path, "clone", "-q", str(bare), str(other / "clone"))
        clone = other / "clone"
        git(clone, "config", "user.name", "Other")
        git(clone, "config", "user.email", "other@example.invalid")
        (clone / "data" / "generated" / "unrelated.json").write_text("{}\n")
        commit_all(clone, "unrelated")
        git(clone, "push", "-q", "origin", "main")

        result = run_script(COMMIT, repo, env=commit_env(bare, stale_head, signing_key))

        assert result.returncode == 1
        assert "main advanced during the update" in result.stdout
        assert not (
            Path(commit_env(bare, stale_head, signing_key)["RUNNER_TEMP"])
            / "iana-data-ci-signing"
        ).exists()

    @pytest.mark.parametrize(
        "missing",
        [
            "CI_SSH_SIGNING_KEY",
            "CI_COMMITTER_NAME",
            "CI_COMMITTER_EMAIL",
            "PUSH_REMOTE",
            "EXPECTED_HEAD",
        ],
    )
    def test_refuses_when_a_required_variable_is_unset(
        self, pushable, tmp_path, signing_key, missing
    ):
        repo, bare = pushable
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        env = commit_env(bare, head, signing_key)
        env[missing] = ""

        result = run_script(COMMIT, repo, env=env)

        assert result.returncode == 1
        assert f"{missing} is not configured" in result.stdout

    def test_removes_the_signing_key_on_success(self, pushable, tmp_path, signing_key):
        repo, bare = pushable
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        patch = make_patch(repo, tmp_path, legitimate_change)
        run_script(APPLY, repo, str(patch))
        env = commit_env(bare, head, signing_key)

        assert run_script(COMMIT, repo, env=env).returncode == 0

        assert not (Path(env["RUNNER_TEMP"]) / "iana-data-ci-signing").exists()

    def test_rejects_an_unexpected_argument(self, pushable, signing_key):
        repo, bare = pushable

        result = run_script(
            COMMIT, repo, "--force", env=commit_env(bare, "x", signing_key)
        )

        assert result.returncode == 2
        assert "unexpected argument" in result.stderr


GIT_STUB = """#!/usr/bin/env bash
# Records what the real git would have received, then stops the script.
{
  printf 'ARGV\\t%s\\n' "$*"
  printf 'GIT_CONFIG_COUNT\\t%s\\n' "${GIT_CONFIG_COUNT:-}"
  printf 'GIT_CONFIG_KEY_0\\t%s\\n' "${GIT_CONFIG_KEY_0:-}"
  printf 'GIT_CONFIG_VALUE_0\\t%s\\n' "${GIT_CONFIG_VALUE_0:-}"
} >> "$GIT_STUB_LOG"
exit 1
"""


@pytest.fixture
def git_stub(tmp_path: Path) -> tuple[Path, Path]:
    """A fake `git` earlier on PATH, plus the file it records into."""
    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    stub = stub_dir / "git"
    stub.write_text(GIT_STUB)
    stub.chmod(0o755)
    return stub_dir, tmp_path / "git-stub.log"


def run_commit_with_stub(stub_dir, log, repo, **env_overrides):
    env = {
        **ISOLATED_GIT_ENV,
        "PATH": f"{stub_dir}:{ISOLATED_GIT_ENV['PATH']}",
        "GIT_STUB_LOG": str(log),
        "RUNNER_TEMP": str(repo.parent / "rt"),
        "PUSH_REMOTE": "https://github.example/o/r.git",
        "EXPECTED_HEAD": "0" * 40,
        "CI_SSH_SIGNING_KEY": "unused-by-the-stub",
        "CI_COMMITTER_NAME": "bot",
        "CI_COMMITTER_EMAIL": "bot@example.invalid",
        **env_overrides,
    }
    Path(env["RUNNER_TEMP"]).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(COMMIT)], cwd=repo, capture_output=True, text=True, check=False, env=env
    )
    return dict(
        line.split("\t", 1) for line in log.read_text().splitlines() if "\t" in line
    )


class TestCredentialHandling:
    def test_token_never_reaches_git_argv(self, git_stub, seeded):
        """A credential in the remote URL would be world readable via /proc."""
        stub_dir, log = git_stub
        token = "ghs_TOKEN_MUST_NOT_APPEAR_IN_ARGV"

        seen = run_commit_with_stub(stub_dir, log, seeded, GH_TOKEN=token)

        assert token not in seen["ARGV"], seen["ARGV"]
        assert "x-access-token" not in seen["ARGV"]

    def test_basic_credential_has_no_trailing_newline(self, git_stub, seeded):
        """`base64 <<< ...` appends a newline, which makes the push 401."""
        stub_dir, log = git_stub
        token = "ghs_EXACTLY_THIS"

        seen = run_commit_with_stub(stub_dir, log, seeded, GH_TOKEN=token)

        assert seen["GIT_CONFIG_COUNT"] == "1"
        assert (
            seen["GIT_CONFIG_KEY_0"]
            == "http.https://github.example/o/r.git.extraheader"
        )
        scheme, encoded = seen["GIT_CONFIG_VALUE_0"].rsplit(" ", 1)
        assert scheme == "Authorization: Basic"
        assert base64.b64decode(encoded) == f"x-access-token:{token}".encode()

    def test_no_auth_config_when_the_token_is_absent(self, git_stub, seeded):
        """The bare-remote path must not inject an empty credential."""
        stub_dir, log = git_stub

        seen = run_commit_with_stub(stub_dir, log, seeded, GH_TOKEN="")

        assert seen["GIT_CONFIG_COUNT"] == ""
        assert seen["GIT_CONFIG_VALUE_0"] == ""
