---
title: The nightly syncs its build inputs instead of refusing the patch
summary: update-data now re-points HEAD at current main and adopts data/manual/ after the scrape, and the consumer guard narrowed to the paths the patch actually writes. The rebase phase measures staleness and script safety from two different commits.
created: 2026-09-10
author: Eric Case
tags: [log, decision, ci, github-actions, signing]
---

# 2026-09-10 - The nightly syncs its build inputs

Run 34410678989 discarded a completed scrape:

    Error: main changed data/ during the run; this patch was built against stale inputs

PR #115 ("Coordinate drift detected") merged at 22:12:11, 3m 30s into a 35-minute run, and
changed one file: `data/manual/places.json`. The guard added on [2026-09-09](2026-09-09-ci-signing-shared.md)
was right to fire - the patch's `data/generated/` had been built from the pre-merge coordinates -
but the whole run was thrown away to avoid publishing one stale field.

## The cost is not where it looked

Measured from the API for that run, not estimated:

| Step                   | Duration |
| ---------------------- | -------- |
| TLD scrape, 8 batches  | 32m 30s  |
| Build `tlds.json`      | 5s       |
| Tests                  | 2m 21s   |
| Patch and upload       | 1s       |

The job holds its inputs for 32 minutes before it reads them. Everything after is under three
minutes. So the fix is not to rebuild after the collision; it is to re-read the inputs
immediately before the only build there is.

## Two changes, doing two different jobs

The old design used one guarded set, `data/`, for two questions it cannot answer at once.

**The guard protects what the patch would overwrite**, and is now `data/source/` plus
`data/generated/` - the same two paths `ci-make-data-patch` packages, so nothing the patch can
express sits outside the guarded set. Scoping the patch matters on its own: a path added
anywhere else under `data/` during the run is absent from this working tree, and a whole-`data/`
diff would have expressed that absence as a deletion. The producer never writes `data/manual/`, so the patch carries no hunks for
it and landing over a concurrent editorial edit preserves that edit. Guarding it bought a
refusal, not protection.

**`ci-land-data-patch sync` keeps the inputs fresh**, and runs in the producer job between the
last scrape batch and the first read. It fetches `main`, and when neither guarded path moved,
`git reset --soft` onto the tip and `git restore --source=<tip> --staged --worktree` over
`data/manual/`. It emits `base_head`, which `sign-data` takes as `EXPECTED_HEAD`.

- **`reset --soft`, not a checkout.** It moves HEAD and leaves the index and working tree
  alone. A detached checkout would swap `src/`, `bin/` and the lockfiles the job is running
  out of. Two earlier drafts justified this wrongly - first that a detached checkout refuses a
  dirty tree, then that it would overwrite the scrape. Neither is true: with the guarded paths
  equal between the two commits it preserves those local modifications. The running code is
  the whole reason.
- **`restore`, not `checkout <tip> -- <path>`.** `git checkout` defaults to overlay mode and
  "never removes files from the index or the working tree", so a file the base branch deleted
  survives in the working tree and the build goes on reading it. `git restore` defaults to
  no-overlay. `3c6b9ec1` deleted three files from `data/manual/`, so this is a real shape, not
  a hypothetical.
- **Sync declines to move when a guarded path moved**, emitting the original `base_head` and a
  warning rather than failing. Adopting there would let the patch revert `main`: this working
  tree never held the new content. The consumer's guard then decides, and the patch artifact
  still uploads.

## rebase now measures two things from two commits

Advancing `EXPECTED_HEAD` past the consumer's own checkout broke an assumption the old code
relied on silently: that `EXPECTED_HEAD` *is* the commit `actions/checkout` produced.

- **Staleness** is `EXPECTED_HEAD..target` over the guarded paths - the patch's base.
- **Script safety** is `HEAD..target` over `bin/` and `.github/` - this job's own checkout,
  which is what `git checkout --detach` is about to overwrite while bash is still reading it.

Measured from `EXPECTED_HEAD`, the CI-code comparison becomes tip-against-tip after a sync and
passes vacuously, and the checkout then swaps the running script. The early exit had the same
defect from the other side: it returned without checking out, which was safe only while the two
commits were the same.

`check-coordinates.yaml` is unchanged and unaffected - it never syncs, so `HEAD` and
`EXPECTED_HEAD` stay equal there and both comparisons collapse to the old one.

## Accepted

- A merge inside the residual window - build, tests, patch, upload, and the `sign-data`
  handoff, about 2m 40s - loses the run only when it touches a guarded path or CI code. An
  editorial merge there now lands and propagates on the next nightly.
- Sync adopts the manual JSON inputs only. Editorial constants in `src/config.py` and
  `src/build/idn_language.py` are code, and the one-nightly code lag accepted on 2026-09-09
  still stands.
- A concurrent human commit to `data/generated/` still loses the run, as before.

## Guards proved by breaking them

Per 2026-09-09, each new guard was watched failing before it was trusted: the overlay checkout
resurrected the deleted file, the CI guard measured from `EXPECTED_HEAD` let the script swap
through, the early exit keyed on `EXPECTED_HEAD` left HEAD behind, and a sync that ignored its
guarded set adopted anyway. All four went red, then green.

One break initially reported green because a `replace(..., 1)` landed on an identical line in
the `sync` phase rather than `rebase`. A break that does not hit the code under test proves
nothing about the test - confirm where it landed, not just that something changed.

`actions/checkout` defaults to `fetch-depth: 1`, and `git restore --source=<tip>` reads a tree
the shallow fetch has to have brought, so the shallow case is covered by a real `--depth=1`
clone rather than the full clones the other cases use. Still uncovered: binary byte-equality
under `data/source/` (the real iptoasn gzip is `.gitignore`d, so it never reaches a patch) and
two consecutive syncs in one run, which the workflow never does.
