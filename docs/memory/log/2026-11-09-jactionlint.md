---
title: bin/lint gained a workflow linter, and the Pushover action stopped templating inputs
summary: jactionlint 2.4.0 is pinned in mise.toml and runs as a bin/lint group and as a test, so CI enforces it too. Clearing its 11 findings moved the Pushover request into bin/ci-send-pushover, which takes its fields from the environment.
created: 2026-11-09
author: Eric Case
tags: [log, decision, ci, lint, jactionlint, pushover]
---

# 2026-11-09 - jactionlint

## The workflows had no linter

`bin/lint` checked Python, shell, JSON and formatting, and nothing read `.github/`. Earlier entries
record `actionlint` being run by hand. `jactionlint --profile default --no-online` is now a `bin/lint`
group, pinned at 2.4.0 in `mise.toml` and required rather than skipped when absent.

No workflow runs `bin/lint`, so `tests/ci/test_workflow_lint.py` runs the same command. `tests.yaml`
installs the `mise.toml` toolchain, which makes the check a merge gate without a new CI step.
`--no-online` keeps both runs off the network.

## What it found

Eleven findings, all older than the change that wired it in:

- **Four `template-injection`** in `.github/actions/pushover/action.yaml`. The action pasted its
  inputs into an inline script, so shell syntax in a title or message would have run. Every caller
  passes fixed strings today, which is why it never bit.
- **Six `unused-job-output`** in the two drift workflows. Removed; the step outputs they mirrored
  are still read inside their own jobs.
- **One `missing-timeout`** on the `Tests` job, now capped at 20 minutes against observed runs of 4
  to 6.

## bin/ci-send-pushover

The action now exports its inputs as `PUSHOVER_*` and calls `bin/ci-send-pushover`, which hands each
field to curl with `--data-urlencode`. The request is form-encoded rather than a hand-built JSON
string, so no value needs escaping. `PUSHOVER_URL` overrides the endpoint; it exists so
`tests/ci/test_ci_send_pushover.py` can drive the script against a local listener.

The script lives in `bin/` rather than beside the action because `bin/lint` finds shell scripts
there by shebang. The action reaches it through `$GITHUB_ACTION_PATH`, so it needs the checkout a
local action already requires.

## Action pins

`TestActionPins` holds every action to a full SHA and to one SHA across workflows. See
[iptoasn freshness](2026-09-24-iptoasn-freshness.md#action-pins-match-across-workflows).
