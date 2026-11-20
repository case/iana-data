---
title: Renovate keeps mise.toml current
summary: Dependabot cannot read mise.toml, so a weekly workflow runs Renovate's mise manager with the job's GITHUB_TOKEN, scoped to that file, its committed mise.lock and the 7-day cooldown.
created: 2026-11-19
author: Eric Case
tags: [log, decision, dependencies, renovate, mise, ci]
---

# 2026-11-19 - Renovate for mise.toml

Dependabot has no mise ecosystem, so `.github/workflows/renovate-mise.yaml` proposes updates to the
tools pinned in `mise.toml`. It runs Mondays at 05:00 UTC and on demand, through the local action
`.github/actions/mise-renovate/`, against this repository only. Dependabot keeps every other
ecosystem, so the two never touch the same file.

## Why Renovate in Actions

- **No candidate tool runs.** Renovate edits `mise.toml` and runs `mise lock`, which downloads and
  hashes each release without unpacking or running it.
- **The cooldown fails closed.** `timestamp-required` holds a release with no date, and
  `internalChecksFilter: strict` creates no branch until the 7 days pass.
- **No stored credential.** The job's `GITHUB_TOKEN` expires with the run.

## mise.lock pins the bytes

The cooldown stops a new malicious release, not an old release whose files were replaced, so
`mise.lock` records a URL and checksum per tool for `linux-x64`, `linux-arm64`, `macos-x64` and
`macos-arm64`. `jdx/mise-action` installs with `--locked` when the file exists, and
`[tool_config] locked = true` makes local installs strict without locking a developer's global
tools. A maintainer creates the lock with `mise lock`; Renovate only refreshes an existing one.

- **Renovate refreshes it in safe mode.** With `mise` absent from `allowedUnsafeExecutions`, Renovate
  44.234.1 runs `mise lock` under `MISE_SAFE=1` and skips `mise trust`, for mise 2026.7.12 and later.
  An older or undetectable mise makes Renovate refuse with a warning, which fails the report check.
- **Failure is visible.** Renovate logs a failed `mise lock` as a warning and exits 0. So
  `check-report.py` fails on any problem in the report, and `check-branches.py` reads each branch
  under the policy's `branchPrefix` back through the API and runs `check-lock.py` on it.
- **One mise.** `mise.toml` sets `min_version`; every `jdx/mise-action` `version` and Renovate's
  `constraints.mise` match it, and a test keeps them equal. No action sets `sha256`, which would
  replace the action's check of mise's signed checksums.
- **Checked offline.** `check-lock.py` is a `bin/lint` group: every tool locked once, at its exact
  pin, with an https URL and a full `sha256`, `blake3` or `sha512` checksum per platform.
- **Python stays uv's.** `idiomatic_version_file_enable_tools = []` stops a developer's global mise
  config from reading `.python-version` and adding Python to this repo's lock.
- **shellcheck's checksums are mise's.** Its release ships no checksum file, so `mise lock` takes them
  from mise's version service (`checksum_source = "mise-versions"`). The other tools' come from the
  publisher: aqua checksum files with attestations, or packslip signatures.
- **Installed trees are trusted.** mise checks downloads, not what is already installed. After
  creating or changing the lock, install once into an empty `MISE_DATA_DIR`.

## The policy file

`renovate-global.json` is the whole policy, and the action's scripts read `reportPath` and
`branchPrefix` from it. `requireConfig: ignored` stops a repository config file overriding it, and
`env-regex` passes only `RENOVATE_REPOSITORIES` and `LOG_LEVEL`, so a caller's `RENOVATE_*`
variables cannot either. `includePaths` limits it to `mise.toml` and `mise.lock`, because the mise
manager also matches `.mise*.toml`, `mise.*.toml` and `.config/mise/**`.

Status checks and the dependency dashboard are off, so the job needs no `statuses` or issue-write
permission. Vulnerability alerts are off because those PRs bypass the release age; Dependabot alerts
cover security. `tests/ci/test_mise_renovate.py` pins the settings that guard security or match
another file, reading the workflow and action through `jactionlint --export-facts`.

## Blast radius

The token has `contents: write`, `pull-requests: write` and `issues: read`; Renovate's startup query
always reads issues. Anything holding the token can push any branch, create releases and edit PRs,
including appending to `main`: the "Signed commits" ruleset blocks only unsigned commits, deletion
and force-push, and an API commit is signed. The config limits what Renovate does, not what the
token allows. The action is pinned by commit and the Renovate image by digest.

`platformCommit: enabled` commits through the GitHub API, which may make the commits verified. If they
are not, merging relies on the Admin `pull_request` bypass on the "Signed commits" ruleset.

## Proving Renovate ran

Renovate exits 0 for a disabled repository and for a failed lookup, which both look like "nothing
to update". `exitCodeForErrors: true` fails the job on a repository error, and `check-report.py`
reads Renovate's JSON report (`reportType: file`). It fails unless the `mise` manager extracted
`mise.toml` with `mise.lock`, extracted as many `depType: tools` entries as `[tools]` declares, and
no tool has a `skipReason`, `lookupFailed` or a warning. It counts tools rather than matching
names, because Renovate can rename a tool. A caller must check out the repository first.

## Upkeep

Dependabot bumps the action's commit pin, because its `github-actions` entry also scans
`/.github/actions/*`. It does not bump the Renovate image in `renovate-image`: rotate that by hand,
to a release at least 7 days old, with its digest. `reportType` is marked experimental, so a
rotation can change the report format; a failing report check is the signal.
