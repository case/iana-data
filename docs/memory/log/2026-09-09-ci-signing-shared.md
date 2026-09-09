---
title: Both CI write paths share one signing layer under bin/
summary: The nightly and the weekly drift flow now run the same produce-patch, rebase, validate, sign, push pipeline. The stale-head guard became a path comparison, and the drift branch is signed and lease-protected.
created: 2026-09-09
author: Eric Case
tags: [log, decision, ci, github-actions, signing, coordinates]
---

# 2026-09-09 - The shared CI signing layer

`update-data.yaml` and `check-coordinates.yaml` both commit to this repository, and until now only the nightly one was hardened. The drift flow committed unsigned as `github-actions[bot]`, pushed with repository hooks live, and authenticated from credentials `actions/checkout` had persisted. This change gives both flows one pipeline: produce a patch, rebase onto current `main`, validate, sign, push.

## Why the drift PR had to be signed

[2026-09-07](2026-09-07-ci-signing.md) scoped the drift branch out, on the reasoning that "a squash or merge produces a GitHub-signed commit". That is wrong, and PR #114 proved it - `mergeStateStatus: BLOCKED`, "Commits must have verified signatures". GitHub evaluates a pull request by building a test merge commit and checking **the commits it introduces, including those on the head branch**, so an unsigned head-branch commit blocks a squash merge even though GitHub would sign the squashed result. The docs add that the restriction "can also apply to the author of the pull request". Source: [`required-signed-commits.md`](https://github.com/github/docs/blob/main/data/reusables/repositories/required-signed-commits.md).

## The shared scripts

| Script | Role |
| ------------------------- | ---------------------------------------------------------------------------- |
| `bin/ci-make-data-patch`  | Producer. Emits `changed`, plus a patch and artifact name when there is one. |
| `bin/ci-apply-data-patch` | Validates an untrusted patch and stages it. Unchanged from 2026-09-07.      |
| `bin/ci-land-data-patch`  | Consumer, in two phases: `rebase` before the key exists, `commit` after.    |

`bin/ci-refresh-coordinates` is the drift producer, split out so the job parsing Wikidata content holds no signing key. `bin/ci-open-drift-pr` lands the patch and then talks to `gh`.

The consumer half was briefly six scripts - a rebase, a signer, a pusher and a sourced auth helper, plus a caller each. They are always run in that one order, so the split bought nothing and cost a sourced file, four usage blocks and four argument parsers: ~370 lines of scaffolding around ~68 lines of work. Merging them removed the sourced helper entirely, which is what the packaging defect below turned on. The one seam that had to stay is the credential boundary, below.

## No composite action

An `.github/actions/apply-signed-commit` composite was planned to hold the repeated YAML and was dropped. **Composite action steps cannot carry `timeout-minutes`**: the runner's [`action_yaml.json`](https://github.com/actions/runner/blob/main/src/Runner.Worker/action_yaml.json) `run-step` mapping accepts only `name`, `id`, `if`, `run`, `env`, `continue-on-error`, `working-directory` and `shell`, and the schema contains no timeout key at all. Extracting the steps would have collapsed their per-step caps into a job cap, and a job cap is a cancellation, which fires no `if: failure()` alert. Fifteen duplicated lines of YAML is the cheaper loss. Revisit only if composite steps gain timeouts.

## The credential boundary is a workflow step, not a process

`bin/ci-apply-data-patch` promises to hold no credentials, and while the pipeline was separate Actions steps that was structurally true. Consolidating it into one process broke it, and the obvious repair - calling the validator through `env -u` - is cosmetic: the child reads the key straight out of the parent's `/proc/<pid>/environ`, which records the environment the parent was *exec'd* with. Verified against a sentinel value.

So `bin/ci-land-data-patch` is one file with two phases, and the workflows run three steps:

1. `ci-land-data-patch rebase` - `GH_TOKEN` and `EXPECTED_HEAD`, no signing key.
2. `ci-apply-data-patch` - nothing at all.
3. `ci-land-data-patch commit` - signing key and token.

`TestCredentialBoundary` asserts it where it now lives: the validator appears in each workflow before the first `CI_SSH_SIGNING_KEY`, no signing key is job-scoped, and `rebase` runs with the signing variables absent. File consolidation and credential isolation are separate axes; collapsing the steps to save a file trades one for the other.

## The stale-head guard became a path comparison

The nightly aborted whenever `main` moved at all. Run 34373003641 died that way: an unrelated `httpx` commit landed 33 minutes into the build, and the guard read commit inequality as danger. The hazard is narrower - a stale patch landing over newer data - so `bin/ci-land-data-patch` compares paths instead and moves HEAD onto the new tip.

- **The guarded set is the flow's generation inputs, not the paths in the patch.** A nightly patch touching only `data/generated/` still depends on `data/manual/`, which `src/build/tlds.py` reads. The nightly guards all of `data/`; the drift flow guards `data/manual`.
- **`bin/` and `.github/` are guarded unconditionally.** A checkout that rewrites them swaps the scripts of the running job, and bash reads a script incrementally rather than up front.
- **Accepted**: rebasing lands data generated by the previous revision's code on top of new code. The window is one nightly.
- A commit landing after the check is caught by the push, which must fast-forward.

Verified on a scratch shallow clone before implementing, since `actions/checkout` defaults to `fetch-depth: 1` and the whole fix rests on diffing two shallow commits: the clean case rebased, and the moved-data case refused.

## The drift branch is machine-owned

`git push -f` overwriting a human commit was listed as accepted in [2026-09-09 drift PR](2026-09-09-coordinate-drift-pr.md). It is now refused, by two checks that do different jobs:

- **Committer identity.** If the remote branch tip was not committed by `CI_COMMITTER_EMAIL`, the run exits 1 with `outcome=branch_diverged`. A lease alone cannot do this: the lease value is read from the same fetch that observes the human commit, so it would approve overwriting what it just saw.
- **`--force-with-lease=refs/heads/<branch>:<sha>`.** Covers the race between that fetch and the push. The `<refname>:<expect>` form names the ref explicitly rather than trusting a remote-tracking branch this job may never have fetched.

## `bin/lib/` was silently ignored

A sourced helper at `bin/lib/ci-git-auth.sh` was swallowed by `.gitignore`: the stock Python `lib/` entry was unanchored, so it matched at any depth. Nothing local caught it - `bin/lint` finds shell scripts on the filesystem by shebang, and the tests read the working tree - but a fresh CI clone would have had no helper and every `bin/ci-*` script would have failed on its `.` line. The helper is now inlined into `bin/ci-land-data-patch`, the ignore is anchored to `/lib/` and `/lib64/`, and `test_ci_data_patch.py` asserts that no `bin/ci-*` path is ignored.

## One-time migration for PR #114

The existing `coordinate-drift` tip `298897f5` was committed by `github-actions[bot]@users.noreply.github.com`, so the new ownership check refuses it and no drift run can replace it. That is the guard working. Adding a legacy-identity allowance was rejected: a permanent hole to serve a single migration outlives the migration. Close PR #114 and delete the branch by hand; the next drift run creates it fresh under the signing identity.

## Guards are proved by breaking them

Seven review rounds ran over this change, and the recurring failure was not a missing guard but an **inert** one: a check written, passing, and unable to fail. The ignore guard used `glob` where the defect was nested, and `git check-ignore` without `--no-index`, which goes quiet the moment a file is tracked. The credential test asserted three of five scrubbed variables. The multi-guard test proved only that the CLI accepted a second `--guard`, not that it enforced one. Each passed on first write.

Every guard here was therefore checked by breaking its subject and confirming it goes red: job-scoping the signing key, re-enabling repository hooks, dropping the ownership check, guarding only `guarded[0]`, swapping `--force-with-lease` for `--force`, restoring the 35-minute cap, restoring `?*)`. Do that for anything added here later; a guard that has never been seen to fail is decoration.

## Still accepted

- A PR opened with `GITHUB_TOKEN` still has check runs awaiting manual approval.
- A curator commit made on the drift branch stops the weekly run rather than being merged into it. Reconciling the two automatically is not attempted.
- `bin/lint` still runs no workflow linter; `actionlint` was run by hand for this change.
