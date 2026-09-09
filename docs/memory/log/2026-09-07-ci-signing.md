---
title: Nightly data commits are signed with a dedicated CI SSH key
summary: update-data hands a validated data-only patch to a clean signing job, which loads CI_SSH_SIGNING_KEY only after validation and pushes a signed commit.
created: 2026-09-07
author: Eric Case
tags: [log, decision, ci, github-actions, signing]
---

# 2026-09-07 - CI commit signing

The `Signed commits` ruleset on `main` (enabled 2026-09-03) rejects unsigned `github-actions[bot]` commits, so `update-data.yaml` separates data update generation from commit signing.

- `update-data` builds with read-only access and `persist-credentials: false`, then uploads a data-only patch (`git diff --no-renames --binary --full-index HEAD -- data/`) as a one-day artifact. The artifact name is a job output, not reconstructed downstream: `run_attempt` increments per run, so a rebuilt name misses the producer's artifact after a failed-jobs re-run.
- `sign-data` runs on a fresh runner with `contents: write` and `persist-credentials: false`, validates the patch, then loads `CI_SSH_SIGNING_KEY` (under `$RUNNER_TEMP`, mode 0600, removed on exit and by an unconditional cleanup step) and commits with hooks disabled.
- `notify-data-committed` sends success notifications holding neither the key nor a write token.

Identity comes from the `CI_COMMITTER_NAME` / `CI_COMMITTER_EMAIL` repository variables; that email must own the public signing key registered with GitHub. The push credential never reaches disk or argv: `PUSH_REMOTE` is credential-free and `GH_TOKEN` is injected as an `http.<url>.extraheader` via `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0`.

The workflow fails early on a missing secret or variable, a `main` that moved during data generation, or a commit with no embedded signature. A stale-head failure survives a re-run - the event payload is reused, so `github.sha` does not move. Recover with `workflow_dispatch` or the next nightly.

Both steps live in `bin/ci-apply-data-patch` and `bin/ci-commit-signed-data` rather than inline `run:` blocks, so shellcheck and `tests/ci/test_ci_data_patch.py` can reach them. See [2026-09-09 shellcheck pin](2026-09-09-shellcheck-pin.md).

## Patch validation

The patch is untrusted, and is checked twice against different sources - the patch headers, then the index. Keep both loops: either alone catches every shape constructible today, but they read different truths.

- **Before applying**: `git apply --numstat -z` lists every path including creations. Each must match `^data/[A-Za-z0-9._/-]+$` with no `..` and no dot-prefixed segment. Any `rename from` header is rejected.
- **After `git apply --cached`**: `git diff --cached --no-renames --name-only -z HEAD`, unscoped, against the same rule, with destination modes limited to `100644` or `000000`.

- **Renames bypass any path check**, since every check sees only the destination. Producer and consumer both pass `--no-renames` and the mode check is unscoped, so a rename's source appears as its own deletion and fails the allowlist.
- **`--cached`, not `--index`**: it never writes the working tree that `uses: ./.github/actions/pushover` resolves against in a job holding `contents: write`. A future gap in the path checks then costs a rejected push, not code execution. It also makes creations visible - plain `git apply` leaves them untracked and `git diff` never lists them, so an additions-only patch reads as "no changes".
- The producer diffs against `HEAD`, not the index: `--intent-to-add` hides deletions from a worktree-versus-index diff.
- The signature check uses process substitution, not a pipe. `grep -q` exits early, SIGPIPEs `git cat-file`, and `pipefail` reads that as unsigned.
- The commit message is passed with `-F`: a full regeneration renders ~70 KB of paths against the 128 KiB `MAX_ARG_STRLEN` cap on a single argv entry.

`tests/ci/test_ci_data_patch.py` drives both scripts against scratch repos with a real `ed25519` key, a real signed commit and a local bare remote, and stubs `git` to assert the token stays out of argv and `.git/config`.

## Timeouts and notifications

Every long step carries its own cap. A job-level timeout is a cancellation, and `if: failure()` does not fire on a cancelled job, so no alert goes out. A job cap must exceed the sum of its step caps or the step guards can never fire: `update-data` sums to 172 under a cap of 190, `sign-data` 14 under 20, `notify-data-committed` 5.

`sign-data` alerts on failure by pushover **and** email, since it is the job that can fail after the data is already built; `update-data` gained a catch-all failure alert covering the patch and upload steps, which had none. Notification steps are `continue-on-error: true` with `timeout-minutes: 2`, and the pushover action's `curl` carries `--max-time 15` so a hung request cannot consume the job before the email fallback runs. The patch and upload steps keep `always()` as a backstop: Actions prefixes `success()` onto any `if` with no status function, so removing `continue-on-error` from a notification step would otherwise skip them and discard a built-and-tested update.

## Superseded

`check-coordinates.yaml` was scoped out here, on the reasoning that it pushes to `coordinate-drift` rather than `main`, "so the ruleset does not block it and a squash or merge produces a GitHub-signed commit". **That was wrong.** GitHub checks the commits a test merge introduces, head-branch commits included, so an unsigned drift commit blocks the squash merge too - which is what happened to PR #114. Both flows now share one signing layer: [2026-09-09 shared CI signing](2026-09-09-ci-signing-shared.md).

The stale-head guard described below was also replaced there, by a path comparison that lets `main` advance.

A GitHub App installation token would remove the long-lived secret and produce commits GitHub signs itself. Rejected on setup cost.
