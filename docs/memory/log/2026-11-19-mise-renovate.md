---
title: Renovate keeps mise.toml current
summary: Dependabot cannot read mise.toml, so a weekly workflow runs Renovate's mise manager with the job's GITHUB_TOKEN, scoped to that file, its committed mise.lock and the 7-day cooldown.
created: 2026-11-19
author: Eric Case
tags: [log, decision, dependencies, renovate, mise, ci]
---

# 2026-11-19 - Renovate for mise.toml

Dependabot has no mise ecosystem, so `.github/workflows/renovate-mise.yaml` runs Renovate on
`mise.toml` and `mise.lock` every Monday at 05:00 UTC and on demand, through the local action
`.github/actions/mise-renovate/`. Dependabot keeps every other ecosystem.

## What it does

- **Opens one grouped PR** for every tool with a release at least 7 days old. A release with no date
  is held.
- **Refreshes `mise.lock`**, which pins a URL and checksum per tool for Linux and macOS on x64 and
  arm64. CI and local installs enforce it, so a replaced release file fails the install.
  Renovate runs `mise lock` in mise's safe mode, so no candidate tool runs.
- **Proves it ran.** Renovate exits 0 when it skips a repository or a lookup fails. `check-report.py`
  reads Renovate's JSON report and fails unless every `[tools]` entry was checked with no problem.
  `check-branches.py` runs `check-lock.py` on each branch Renovate pushed.
- **Uses one policy.** `renovate-global.json` is the whole config; a repository config file and
  caller `RENOVATE_*` variables cannot override it. The scripts read `reportPath` and `branchPrefix`
  from it.

## Why this shape

- **No stored credential.** The job's `GITHUB_TOKEN` expires with the run.
- **One mise.** `mise.toml` `min_version`, every `jdx/mise-action` version and Renovate's
  `constraints.mise` agree; `tests/ci/test_mise_lock.py` keeps them equal.
- **Blast radius.** The token has `contents: write`, `pull-requests: write` and `issues: read`, so
  anything holding it can push branches. The action is pinned by commit and the image by digest.

## Upkeep

Dependabot bumps the action's pin. Rotate the Renovate image by hand, to a release at least 7 days
old, with its digest. After changing `mise.lock`, install once into an empty `MISE_DATA_DIR`.
