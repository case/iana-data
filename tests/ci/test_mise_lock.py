"""mise.lock pins the bytes of every mise.toml tool, and CI installs them with one pinned mise."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
MISE_TOML = REPO_ROOT / "mise.toml"
CHECK_LOCK = REPO_ROOT / ".github" / "actions" / "mise-renovate" / "check-lock.py"
PLATFORMS = ["linux-x64", "linux-arm64", "macos-x64", "macos-arm64"]
CHECKSUM = "sha256:" + "ab" * 32


def run_check(mise_path: Path, lock_path: Path):
    return subprocess.run(
        [sys.executable, "-I", str(CHECK_LOCK), str(mise_path), str(lock_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def mise_toml(tools: str, platforms: list[str] | None = None) -> str:
    platforms = ["linux-x64", "macos-arm64"] if platforms is None else platforms
    return (
        f"[settings]\nlockfile_platforms = {json.dumps(platforms)}\n\n[tools]\n{tools}"
    )


def lock_entry(
    name: str,
    version: str,
    platforms: tuple[str, ...] = ("linux-x64", "macos-arm64"),
    url: str = "https://example.test/tool.tar.gz",
    checksum: str = CHECKSUM,
) -> str:
    entry = f'[[tools.{name}]]\nversion = "{version}"\nbackend = "aqua:x/{name}"\n\n'
    for platform in platforms:
        entry += f'[tools.{name}."platforms.{platform}"]\nchecksum = "{checksum}"\nurl = "{url}"\n\n'
    return entry


def check(tmp_path: Path, mise: str | None, lock: str | None):
    mise_path, lock_path = tmp_path / "mise.toml", tmp_path / "mise.lock"
    if mise is not None:
        mise_path.write_text(mise, encoding="utf-8")
    if lock is not None:
        lock_path.write_text(lock, encoding="utf-8")
    return run_check(mise_path, lock_path)


GOOD_TOOLS = 'uv = "0.13.5"\ndprint = "0.57.4"\n'
GOOD_LOCK = (
    "lockfile_version = 4\n\n"
    + lock_entry("uv", "0.13.5")
    + lock_entry("dprint", "0.57.4")
)


def test_a_lock_covering_every_tool_and_platform_passes(tmp_path):
    result = check(tmp_path, mise_toml(GOOD_TOOLS), GOOD_LOCK)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "all 2 tools" in result.stdout


def test_the_table_form_of_a_pin_is_read(tmp_path):
    tools = 'uv = { version = "0.13.5" }\ndprint = "0.57.4"\n'
    result = check(tmp_path, mise_toml(tools), GOOD_LOCK)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("mise", "lock", "expected"),
    [
        (mise_toml(GOOD_TOOLS), lock_entry("uv", "0.13.5"), "0 entries for dprint"),
        (
            mise_toml('uv = "0.13.5"\n'),
            GOOD_LOCK,
            "mise.lock has dprint, which mise.toml no longer declares",
        ),
        (
            mise_toml(GOOD_TOOLS),
            lock_entry("uv", "0.13.4") + lock_entry("dprint", "0.57.4"),
            "locks uv at 0.13.4, mise.toml pins 0.13.5",
        ),
        (
            mise_toml(GOOD_TOOLS),
            GOOD_LOCK + lock_entry("uv", "0.13.5"),
            "2 entries for uv",
        ),
        (
            mise_toml(GOOD_TOOLS, ["linux-x64", "linux-arm64"]),
            GOOD_LOCK,
            "uv has no checksum for linux-arm64",
        ),
        (
            mise_toml(GOOD_TOOLS),
            lock_entry("uv", "0.13.5", url="http://example.test/uv.tar.gz")
            + lock_entry("dprint", "0.57.4"),
            "uv has no https URL for linux-x64",
        ),
        (
            mise_toml(GOOD_TOOLS),
            lock_entry("uv", "0.13.5", checksum="sha256:")
            + lock_entry("dprint", "0.57.4"),
            "uv has no checksum for linux-x64",
        ),
        (
            mise_toml(GOOD_TOOLS),
            lock_entry("uv", "0.13.5", checksum="sha256:" + "ab" * 16)
            + lock_entry("dprint", "0.57.4"),
            "uv has no checksum for linux-x64",
        ),
        (
            mise_toml(GOOD_TOOLS),
            lock_entry("uv", "0.13.5", checksum="md5:" + "ab" * 16)
            + lock_entry("dprint", "0.57.4"),
            "uv has no checksum for linux-x64",
        ),
        (mise_toml(GOOD_TOOLS, []), GOOD_LOCK, "no [settings] lockfile_platforms"),
        (mise_toml(""), GOOD_LOCK, "declares no [tools]"),
        (
            mise_toml('uv = ""\ndprint = "0.57.4"\n'),
            GOOD_LOCK,
            "uv has no exact version",
        ),
        (
            mise_toml(GOOD_TOOLS),
            lock_entry("uv", "0.13.5", url="https:///uv.tar.gz")
            + lock_entry("dprint", "0.57.4"),
            "uv has no https URL for linux-x64",
        ),
        (mise_toml('uv = { os = ["linux"] }\n'), "", "uv has no exact version"),
        (None, GOOD_LOCK, "cannot read"),
        (mise_toml(GOOD_TOOLS), None, "cannot read"),
        (mise_toml(GOOD_TOOLS), "[[tools.uv]\n", "cannot read"),
    ],
    ids=[
        "tool-unlocked",
        "stale-extra-tool",
        "version-behind-pin",
        "duplicate-entry",
        "platform-missing",
        "plain-http",
        "empty-checksum",
        "truncated-sha256",
        "weak-algorithm",
        "no-platforms",
        "no-tools",
        "empty-pin",
        "https-without-host",
        "no-version",
        "no-mise-toml",
        "no-lock",
        "malformed-lock",
    ],
)
def test_a_lock_that_does_not_cover_mise_toml_fails(tmp_path, mise, lock, expected):
    result = check(tmp_path, mise, lock)
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert expected in result.stdout


def test_mise_toml_locks_this_repo_on_every_common_platform():
    settings = tomllib.loads(MISE_TOML.read_text(encoding="utf-8"))
    assert settings["settings"]["lockfile"] is True
    assert settings["settings"]["lockfile_platforms"] == PLATFORMS
    # tool_config scopes strict installs to this repo; [settings] locked would also lock global tools.
    assert settings["tool_config"]["locked"] is True
    assert "locked" not in settings["settings"]
    # Otherwise a developer whose global config enables .python-version locks an extra tool.
    assert settings["settings"]["idiomatic_version_file_enable_tools"] == []


def test_ci_and_renovate_run_the_min_version_of_mise():
    """One mise everywhere, so CI and Renovate read and write the lock format mise.toml was written for."""
    min_version = tomllib.loads(MISE_TOML.read_text(encoding="utf-8"))["min_version"]
    policy = json.loads(
        (CHECK_LOCK.parent / "renovate-global.json").read_text(encoding="utf-8")
    )
    assert policy["constraints"] == {"mise": min_version}
    binary = shutil.which("jactionlint")
    assert binary, "jactionlint not on PATH; run `mise install`"
    facts = json.loads(
        subprocess.run(
            [binary, "--export-facts", "--no-online"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    steps = [
        (workflow["path"], step)
        for workflow in facts["workflows"]
        for job in workflow["jobs"]
        for step in job["steps"]
        if step.get("uses", {}).get("repository") == "jdx/mise-action"
    ]
    assert len(steps) >= 4, steps
    for path, step in steps:
        inputs = {item["name"]: item["value"] for item in step.get("inputs", [])}
        assert inputs.get("version") == min_version, path
        # sha256 would replace the action's check of mise's signed checksums.
        assert "sha256" not in inputs, path


def test_a_sha512_checksum_is_accepted(tmp_path):
    lock = lock_entry("uv", "0.13.5", checksum="sha512:" + "ab" * 64) + lock_entry(
        "dprint", "0.57.4"
    )
    result = check(tmp_path, mise_toml(GOOD_TOOLS), lock)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_blake3_checksum_is_accepted(tmp_path):
    lock = lock_entry("uv", "0.13.5", checksum="blake3:" + "ab" * 32) + lock_entry(
        "dprint", "0.57.4"
    )
    result = check(tmp_path, mise_toml(GOOD_TOOLS), lock)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_backend_prefixed_tool_matches_its_registry_lock_key(tmp_path):
    """mise files `core:node` under `node`; it is neither missing nor stale."""
    tools = '"core:node" = "24.21.0"\n'
    result = check(tmp_path, mise_toml(tools), lock_entry("node", "24.21.0"))
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_backend_prefixed_tool_locked_under_its_full_name_matches(tmp_path):
    tools = '"aqua:jdx/jactionlint" = "2.4.0"\n'
    lock = lock_entry("jactionlint", "2.4.0").replace(
        "tools.jactionlint", 'tools."aqua:jdx/jactionlint"'
    )
    result = check(tmp_path, mise_toml(tools), lock)
    assert result.returncode == 0, result.stdout + result.stderr


CHECK_BRANCHES = CHECK_LOCK.with_name("check-branches.py")
REPO = "case/iana-data"
# Not the shipped policy's prefix, so a prefix hard-coded in the script finds no branches.
PREFIX = "lock-check/"
# Answers only the endpoints a test serves, and file contents only when asked for raw bytes.
FAKE_GH = """
import json, sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

endpoint = urlsplit(sys.argv[-1])
key = endpoint.path + "".join(f"?ref={ref}" for ref in parse_qs(endpoint.query).get("ref", []))
served = json.loads(Path(__file__).with_name("served.json").read_text())
raw = "Accept: application/vnd.github.raw+json" in sys.argv
if key not in served or ("/contents/" in key and not raw):
    sys.exit("gh: Not Found (HTTP 404)")
print(served[key], end="")
"""
GOOD_BRANCH = (mise_toml(GOOD_TOOLS), GOOD_LOCK)


def serve(branches: dict[str, tuple[str, str]]) -> dict[str, str]:
    """The ref listing for PREFIX, then each branch's mise.toml and mise.lock."""
    refs = [{"ref": f"refs/heads/{branch}"} for branch in branches]
    served = {f"repos/{REPO}/git/matching-refs/heads/{PREFIX}": json.dumps(refs)}
    for branch, (mise, lock) in branches.items():
        served[f"repos/{REPO}/contents/mise.toml?ref={branch}"] = mise
        served[f"repos/{REPO}/contents/mise.lock?ref={branch}"] = lock
    return served


def check_branches(tmp_path: Path, served: dict[str, str]):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "served.json").write_text(json.dumps(served), encoding="utf-8")
    gh = bin_dir / "gh"
    gh.write_text(f"#!{sys.executable}\n{FAKE_GH}", encoding="utf-8")
    gh.chmod(0o755)
    policy = tmp_path / "renovate-global.json"
    policy.write_text(json.dumps({"branchPrefix": PREFIX}), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-I", str(CHECK_BRANCHES), str(policy), REPO],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        check=False,
    )


def test_every_branch_under_the_policy_prefix_is_checked(tmp_path):
    branches = {f"{PREFIX}mise-tools": GOOD_BRANCH, f"{PREFIX}uv": GOOD_BRANCH}
    result = check_branches(tmp_path, serve(branches))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Checked 2 Renovate branch(es)" in result.stdout


def test_no_open_branch_passes(tmp_path):
    """No branch means Renovate found nothing to update."""
    result = check_branches(tmp_path, serve({}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Checked 0 Renovate branch(es)" in result.stdout


def test_a_branch_whose_lock_trails_its_mise_toml_fails(tmp_path):
    """The case a failed `mise lock` leaves: mise.toml bumped, mise.lock not."""
    bumped = mise_toml('uv = "0.13.6"\ndprint = "0.57.4"\n')
    branches = {f"{PREFIX}a": GOOD_BRANCH, f"{PREFIX}b": (bumped, GOOD_LOCK)}
    result = check_branches(tmp_path, serve(branches))
    assert result.returncode == 1
    assert "locks uv at 0.13.5, mise.toml pins 0.13.6" in result.stdout


@pytest.mark.parametrize(
    "unserved",
    [
        f"repos/{REPO}/git/matching-refs/heads/{PREFIX}",
        f"repos/{REPO}/contents/mise.lock?ref={PREFIX}a",
    ],
    ids=["ref-listing", "branch-file"],
)
def test_a_failed_api_call_fails(tmp_path, unserved):
    served = serve({f"{PREFIX}a": GOOD_BRANCH})
    del served[unserved]
    result = check_branches(tmp_path, served)
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert "HTTP 404" in result.stdout
