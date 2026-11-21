"""The mise-renovate action's policy file holds the job to mise.toml, its lock, safe-mode mise and a 7-day wait."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
ACTION_DIR = REPO_ROOT / ".github" / "actions" / "mise-renovate"
POLICY = ACTION_DIR / "renovate-global.json"
CHECK_REPORT = ACTION_DIR / "check-report.py"
WORKFLOW = ".github/workflows/renovate-mise.yaml"
ACTION = ".github/actions/mise-renovate/action.yaml"
RENOVATE_ACTION = "renovatebot/github-action"


@pytest.fixture(scope="module")
def policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def facts() -> dict:
    """The workflows and actions as jactionlint parses them, so no test matches YAML text."""
    binary = shutil.which("jactionlint")
    assert binary, "jactionlint not on PATH; run `mise install`"
    result = subprocess.run(
        [binary, "--export-facts", "--no-online"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def by_path(entries: list[dict], path: str) -> dict:
    matches = [entry for entry in entries if entry["path"] == path]
    assert len(matches) == 1, f"{path}: {len(matches)} entries"
    assert matches[0]["parsed"], f"{path} did not parse"
    return matches[0]


@pytest.fixture(scope="module")
def renovate_inputs(facts) -> dict[str, str]:
    """Inputs of the one step that runs Renovate; a decoy step elsewhere cannot satisfy these tests."""
    steps = by_path(facts["actions"], ACTION)["steps"]
    renovate = [
        step
        for step in steps
        if step.get("uses", {}).get("repository") == RENOVATE_ACTION
    ]
    assert len(renovate) == 1, renovate
    assert renovate[0]["uses"]["ref_kind"] == "full-sha"
    # Clear the stale report, run Renovate, check the report, check the branches: no other action runs.
    assert [step["kind"] for step in steps] == ["run", "action", "run", "run"]
    return {item["name"]: item["value"] for item in renovate[0]["inputs"]}


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        # A repo config file could otherwise override every setting below.
        ("requireConfig", "ignored"),
        ("onboarding", False),
        ("enabledManagers", ["mise"]),
        ("includePaths", ["mise.toml", "mise.lock"]),
        # Empty keeps `mise lock` in MISE_SAFE mode; listing mise would add `mise trust`.
        ("allowedUnsafeExecutions", []),
        ("rangeStrategy", "pin"),
        ("minimumReleaseAge", "7 days"),
        ("minimumReleaseAgeBehaviour", "timestamp-required"),
        ("internalChecksFilter", "strict"),
        # Vulnerability PRs would carry their own minimumReleaseAge.
        ("vulnerabilityAlerts", {"enabled": False}),
        ("separateMajorMinor", False),
        ("groupName", "mise tools"),
        ("prConcurrentLimit", 1),
        ("branchConcurrentLimit", 1),
        ("dependencyDashboard", False),
        ("platformCommit", "enabled"),
        # Without it, a repository run that ends in an error can still exit 0.
        ("exitCodeForErrors", True),
        # check-report.py reads this file; the action mounts the runner's /tmp into the container.
        ("reportType", "file"),
        ("reportPath", "/tmp/renovate-report.json"),
    ],
)
def test_policy_setting(policy, key, expected):
    assert policy.get(key) == expected


def test_lock_updates_are_not_skipped(policy):
    """Absent, not false or null: a skipped lock update would leave mise.lock behind mise.toml."""
    assert "skipArtifactsUpdate" not in policy


def test_every_status_check_is_off(policy):
    """The job grants no statuses permission, so a status write would fail the run."""
    checks = policy["statusCheckWhen"]
    assert set(checks) == {
        "artifactError",
        "configValidation",
        "mergeConfidence",
        "minimumReleaseAge",
    }
    assert set(checks.values()) == {"never"}


def test_branch_prefix_is_not_renovate_default(policy):
    """The default would collide with any Renovate app installed on the same repo."""
    assert policy["branchPrefix"] != "renovate/"
    assert policy["branchPrefix"].endswith("/")


def test_renovate_image_is_pinned_by_digest(renovate_inputs):
    """A tag can be re-pushed; only a digest makes the container immutable."""
    image = renovate_inputs["renovate-image"]
    assert re.fullmatch(
        r"ghcr\.io/renovatebot/renovate:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", image
    ), image


def test_only_named_variables_reach_the_container(renovate_inputs):
    """The action's default env-regex passes every RENOVATE_* variable, which could override the policy file."""
    pattern = renovate_inputs["env-regex"]
    assert pattern == "^(?:RENOVATE_REPOSITORIES|LOG_LEVEL)$"


def test_renovate_reads_the_shipped_policy_file(renovate_inputs):
    assert (
        renovate_inputs["configurationFile"]
        == "${{ github.action_path }}/renovate-global.json"
    )


def test_workflow_grants_exactly_what_renovate_needs(facts):
    """Every scope is a write the token could misuse; issues read is for Renovate's startup query."""
    workflow = by_path(facts["workflows"], WORKFLOW)
    assert workflow["permissions"]["scopes"] == {"*": "none"}
    assert sorted(event["name"] for event in workflow["events"]) == [
        "schedule",
        "workflow_dispatch",
    ]
    (job,) = workflow["jobs"]
    assert job["effective_permissions"]["scopes"] == {
        "contents": "write",
        "issues": "read",
        "pull-requests": "write",
    }


REPO = "case/iana-data"
MISE_TOML = '[tools]\nuv = "0.13.5"\ndprint = "0.57.4"\n'


def tool(name: str, **fields) -> dict:
    """An extracted top-level tool after a clean lookup, unless fields say otherwise."""
    return {
        "depName": name,
        "depType": "tools",
        "currentValue": "1.0.0",
        "updates": [],
        **fields,
    }


def report_with(repo_entry: dict | None) -> dict:
    repositories = {} if repo_entry is None else {REPO: repo_entry}
    return {"problems": [], "repositories": repositories}


def processed(*deps: dict, **overrides) -> dict:
    deps = deps or (tool("uv"), tool("dprint"))
    entry = {
        "status": "onboarded",
        "problems": [],
        "branches": [],
        "packageFiles": {
            "mise": [
                {
                    "packageFile": "mise.toml",
                    "lockFiles": ["mise.lock"],
                    "deps": list(deps),
                }
            ]
        },
    }
    entry.update(overrides)
    return entry


def run_check(
    tmp_path: Path,
    report: dict | str | None,
    repository: str = REPO,
    mise_toml: str | None = MISE_TOML,
    clear: bool = False,
):
    """Run check-report.py as the action does; a str report is written verbatim, None is left absent."""
    report_path = tmp_path / "renovate-report.json"
    if report is not None:
        report_path.write_text(
            report if isinstance(report, str) else json.dumps(report), encoding="utf-8"
        )
    mise_path = tmp_path / "mise.toml"
    if mise_toml is not None:
        mise_path.write_text(mise_toml, encoding="utf-8")
    policy_path = tmp_path / "renovate-global.json"
    policy_path.write_text(
        json.dumps({"reportPath": str(report_path)}), encoding="utf-8"
    )
    args = ["--clear"] if clear else [repository, str(mise_path)]
    return subprocess.run(
        [sys.executable, "-I", str(CHECK_REPORT), str(policy_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_every_declared_tool_checked_passes(tmp_path):
    report = report_with(
        processed(tool("uv", updates=[{"newValue": "0.14.0"}]), tool("dprint"))
    )
    result = run_check(tmp_path, report)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "all 2 tools" in result.stdout


def test_a_renamed_tool_still_counts(tmp_path):
    """Renovate can give a tool a configured depName; only a missing tool should fail."""
    result = run_check(
        tmp_path, report_with(processed(tool("astral-sh/uv"), tool("dprint")))
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (None, "unreadable"),
        ("{not json", "unreadable"),
        (report_with(None), f"no entry for {REPO}"),
        (report_with(processed(status="disabled", packageFiles={})), "disabled"),
        (report_with(processed(packageFiles={})), "did not extract mise.toml"),
        (
            report_with(
                processed(
                    packageFiles={
                        "mise": [{"packageFile": ".mise.toml", "deps": [tool("uv")]}]
                    }
                )
            ),
            "did not extract mise.toml",
        ),
        (
            report_with(processed(tool("uv"))),
            "declares 2 tools but Renovate extracted 1",
        ),
        (
            report_with(
                processed(tool("uv"), tool("node", depType="task-build-tools"))
            ),
            "declares 2 tools but Renovate extracted 1",
        ),
    ],
    ids=[
        "missing",
        "malformed",
        "other-repo",
        "disabled",
        "no-mise",
        "wrong-file",
        "partial",
        "task-tool-not-counted",
    ],
)
def test_a_report_that_does_not_prove_processing_fails(tmp_path, report, expected):
    result = run_check(tmp_path, report)
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert expected in result.stdout


@pytest.mark.parametrize(
    ("bad_tool", "expected"),
    [
        (
            # The shape Renovate's fetch.ts gives a dependency whose lookup hit an external host error.
            tool(
                "uv",
                lookupFailed=True,
                warnings=[{"topic": "Lookup Error", "message": "uv: 503"}],
            ),
            "uv lookup failed",
        ),
        (
            tool("uv", warnings=[{"topic": "Lookup Error", "message": "uv: 503"}]),
            "uv: Lookup Error: uv: 503",
        ),
        (
            tool("uv", skipReason="unsupported-datasource"),
            "uv was skipped: unsupported-datasource",
        ),
    ],
    ids=["lookup-failed", "warning-only", "skipped"],
)
def test_a_tool_renovate_could_not_check_fails(tmp_path, bad_tool, expected):
    """One unchecked tool fails the run, even when the others are clean."""
    result = run_check(tmp_path, report_with(processed(bad_tool, tool("dprint"))))
    assert result.returncode == 1
    assert expected in result.stdout


@pytest.mark.parametrize(
    ("mise_toml", "expected"),
    [
        (None, "check out the repository"),
        ("[tools\n", "check out the repository"),
        ("[env]\n", "declares no [tools]"),
    ],
    ids=["absent", "malformed", "no-tools"],
)
def test_an_unusable_mise_toml_fails(tmp_path, mise_toml, expected):
    result = run_check(tmp_path, report_with(processed()), mise_toml=mise_toml)
    assert result.returncode == 1
    assert expected in result.stdout


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (
            # Renovate records a failed `mise lock` as a warning-level problem and exits 0.
            report_with(
                processed(problems=[{"level": 40, "msg": "Artifact update problem"}])
            ),
            "Renovate reported a problem: Artifact update problem",
        ),
        (
            {
                "problems": [{"level": 50, "msg": "Repository has an error"}],
                "repositories": {REPO: processed()},
            },
            "Renovate reported a problem: Repository has an error",
        ),
        (
            report_with(
                processed(
                    packageFiles={
                        "mise": [
                            {
                                "packageFile": "mise.toml",
                                "deps": [tool("uv"), tool("dprint")],
                            }
                        ]
                    }
                )
            ),
            "did not associate mise.lock with mise.toml",
        ),
    ],
    ids=["repo-problem", "global-problem", "no-lock-file"],
)
def test_a_lock_update_renovate_could_not_prove_fails(tmp_path, report, expected):
    result = run_check(tmp_path, report)
    assert result.returncode == 1
    assert expected in result.stdout


def test_a_report_left_by_an_earlier_job_cannot_pass(tmp_path):
    """The action clears the policy's reportPath before Renovate runs; one that writes nothing then fails."""
    cleared = run_check(tmp_path, report_with(processed()), clear=True)
    assert cleared.returncode == 0, cleared.stdout + cleared.stderr
    result = run_check(tmp_path, None)
    assert result.returncode == 1
    assert "unreadable" in result.stdout


def test_a_policy_without_a_report_path_fails(tmp_path):
    (tmp_path / "renovate-global.json").write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(CHECK_REPORT),
            str(tmp_path / "renovate-global.json"),
            "--clear",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "names no readable reportPath" in result.stdout


def test_a_report_that_cannot_be_cleared_fails(tmp_path):
    """A stale report the job cannot delete would otherwise be read as this run's."""
    (tmp_path / "renovate-report.json").mkdir()
    result = run_check(tmp_path, None, clear=True)
    assert result.returncode == 1
    assert "cannot clear the earlier report" in result.stdout
