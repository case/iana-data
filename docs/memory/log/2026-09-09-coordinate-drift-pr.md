---
title: The drift check opens its PR through bin/ci-open-drift-pr and alerts on every outcome
summary: gh pr create is refused unless the repo allows Actions to create PRs, and the old notify step was gated on that success, so the first real drift produced a stranded branch and no alert. The step logic moved to a script that degrades to a compare URL, and each outcome now has its own notification.
created: 2026-09-09
author: Eric Case
tags: [log, decision, ci, github-actions, coordinates, notifications]
---

# 2026-09-09 - Coordinate drift PR and its alerts

`check-coordinates.yaml` runs weekly (Mondays 04:00 UTC) and had never opened a PR: the five runs before 2026-09-07 found no drift, so the path was unexercised. Run 34102537209 found `DRIFT miami`, pushed `coordinate-drift`, and then failed with `GitHub Actions is not permitted to create or approve pull requests (createPullRequest)`. Personal-account repos disallow that by default; the repository setting is now enabled.

No alert fired, and would not have under any failure. The notify step read `if: steps.check.outcome == 'failure' && steps.pr.outputs.pr_created == 'true'`, which fails two ways at once: the `if` carries no status function so Actions prefixes `success()`, and `pr_created` was only written after a successful `gh pr create`. The branch sat unmerged and unannounced.

## What changed

The step logic moved to `bin/ci-open-drift-pr`. `tests/ci/test_ci_open_drift_pr.py` drives it against scratch repos with a bare remote and a stubbed `gh`.

- **A refused `gh pr create` is no longer fatal.** The branch is pushed either way, and the step emits `outcome=pr_blocked` plus a compare URL that the notification carries. The alert survives any reason PR creation fails, not just this one.
- **Notifications key on new content, not on PR existence.** The script compares `data/manual` against the same subtree on the remote branch, and announces only when they differ, so an unresolved drift does not re-notify weekly. The **root** tree cannot be that key: every run branches off a `main` that moved overnight, so a root-tree comparison reports new content every week.
- **Pushing and announcing are separate decisions.** The branch is force-pushed every run so it stays rebased on current `main` and mergeable; only the subtree comparison decides whether an alert goes out. Gating the push on the same key strands the branch on a stale base as soon as a curator edits the same file.
- **Each outcome has its own alert** - PR opened or updated, PR blocked, refresh could not fix the drift, Wikidata unreachable, and a catch-all `if: failure()`. All are `continue-on-error: true` with `timeout-minutes: 2`, matching `update-data.yaml`. A following step fails the job when **any** of the four alerts has `outcome == 'failure'`, so an undelivered alert turns the run red and reaches the owner through GitHub's own scheduled-failure email rather than the channel that just failed. Every tolerated notification needs an `id` and a place in that guard, or the alert it carries can fail while the job stays green.
- **Drift and fetch failure are separated.** `_run_check` returns 1 for either, so the step counts `DRIFT` and `FAIL` lines and publishes both. A pure outage skips the refresh entirely and alerts; before, it refreshed nothing, exited 0, and looked like a clean week.
- **Exit 1 is not taken as proof the check ran.** A crash and a missing `places.json` also exit 1, with an empty report and both counts zero, which read as a clean week. The step requires the check's own `coordinate check: ` summary line before trusting the counts.
- **A refresh that fixes nothing has its own outcome.** Drift found, refresh unable to fetch that place, no file changes: previously `no_changes` and silence, on the loudest case there is.
- **`_run_fetch` returns 1 when any place could not be fetched, or when a write reported `error`.** It returned 0 unconditionally, so "a diff exists" read as "the drift is fixed" even when the refresh had failed on the drifted place and merely jittered another. `write_json_if_changed` swallows write errors into an `"error"` status, so a fetched-but-unpersisted refresh was the same silent zero. The script flags a partial refresh in the PR body.

## Carried in the same change

- `.github/actions/pushover` gained `--fail-with-body`. Without it a rejected token exits 0, which is how the [2026-08-18](2026-08-18-hgtld-retired.md) failure went undelivered. Affects all 12 call sites; a rejected send now shows as a tolerated failed step rather than a green one.
- `tests.yaml` path filters gained `bin/**` and `scripts/**`. A fix to any `bin/ci-*` script alone did not trigger the suite that tests it, which silently applied to the signing scripts too.

## Known and accepted

- PRs opened with `GITHUB_TOKEN` create check runs in an [approval-required state](https://docs.github.com/en/actions/concepts/security/github_token), so the drift PR's tests wait for a manual approval. The PR body says so.
- ~~`git push -f` still overwrites human commits pushed onto `coordinate-drift` between weekly runs.~~ Closed by the committer check and the lease in [2026-09-09 shared CI signing](2026-09-09-ci-signing-shared.md), which also signs the drift commit so the PR can be merged at all.
- A drift alert that fails to send on unchanged content is not retried the following week; the job goes red instead, which is the signal.
- A permanently blocked `gh pr create` re-alerts weekly even on unchanged content, because a pushed branch with no PR is an unresolved state needing manual action. That is a deliberate exception to "announce new content only".
- `bin/lint` runs no YAML or workflow linter; `actionlint` was run by hand for this change.
