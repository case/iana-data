# iptoasn freshness: a real timestamp, and a field that lies

Every decision an implementer would otherwise have to invent is made here rather than deferred.

## Problem

The ASN health gate asks whether the artifact is **good**, never whether it is **recent**. The
consumer takes the latest successful producer run with no age check and artifacts live 45 days
(`update-iptoasn.yaml:42`), so a prolonged producer outage leaves a stale but healthy-looking
artifact eligible. M3 deferred an age gate deliberately: the only timestamp it could see was the
gzip header mtime, an artifact of compression rather than a published convention, and
`now - mtime <= limit` accepts a future timestamp.

**Exposure today is small but not bounded the way the first draft claimed.** The producer alerts on
failure (`update-iptoasn.yaml:47`) and measured `as_org` churn is 0-16 addresses of ~8,950 a night.
But 45-day artifact expiry is **not** a backstop on published ASN age.

**Corrected mechanism.** An earlier draft said preserve mode copies committed values indefinitely.
That is not the path: `data/source/icann-gtlds.json` changes in essentially every nightly commit
(12 of the last 12), so `source_changed=true` nightly and a healthy artifact takes `--all` every
night. The real exposure is therefore that a 40-day-old artifact's labels get published **as current
enrichment**, not that they get preserved. Preserve-forever needs `healthy=false`, which already
alerts (`update-data.yaml:269-278`).

What the gate buys is consequently narrower than "fresh published output": after it, a stale artifact
flips the nightly to preserve - which publishes stale labels too - so the value is the alert, and
not archiving labels that are still live. `last_downloaded` stalling is what makes the staleness
visible; see "The field is populated, not removed".

## Current state: the field does not measure what its name says

`data/generated/metadata.json` carries `IPTOASN.last_downloaded`:

- Written only by `download_iptoasn()` (`src/utilities/download.py:266`), reachable through
  `--download-iptoasn` (`src/cli.py:71`) and the `make` target wrapping it. No workflow invokes it.
- The producer fetches with raw `curl` (`update-iptoasn.yaml:25`) and commits nothing. The consumer
  downloads the artifact and never touches metadata.
- Observed: `2026-05-25T18:06:26Z` for 106 days, then `2026-09-09T03:06:28Z` from a local run in
  `604d80eb`, unchanged since. Two manual runs, not a mechanism.
- **No production code reads it.** `is_cache_fresh` (`src/utilities/cache.py:24`) needs a
  `cache_data` wrapper this entry lacks.

**Removal was reversed; this section is kept for the history.** One test reads the field, and
`bin/test` gates the nightly patch (`update-data.yaml:321`):

- `tests/utilities/test_download.py:894` asserts the field exists after a download. This is the
  only adaptation removal requires.
- `tests/build/test_tlds.py:489` writes its **own** sentinel to a temp path and compares that
  (`:493`, `:505`). It never reads the published field and is unaffected. An earlier draft of this
  plan wrongly listed it.

Removing the writer alone does not remove the published field: `load_metadata`/`save_metadata`
preserve existing keys (`src/utilities/metadata.py:28-49`), so the committed value must be edited
out too.

## Proposed solution

**Use the producer run's timestamp.** The consumer already queries that run to find the artifact:

```
gh run list --workflow=update-iptoasn.yaml --status=success --limit=1 --json databaseId
```

One more field yields GitHub's own record of when the artifact was produced: server-generated, so
not skewed by the producer's clock, and needing no producer change, no sidecar and no trust in gzip
internals.

**Scope, stated narrowly:** this is a **producer-run recency gate**. It does not establish that
upstream data is fresh - an upstream server returning the same old dataset daily gets a new run
timestamp every night and passes. Upstream freshness stays unverified, as M3 already recorded.

- [x] Add the timestamp to the run query and pass it to the health check as
      `--artifact-created-at`. **Absent means the recency check does not run**, which keeps the
      existing health tests and local runs working unchanged
      (`tests/test_check_asn_drift.py:388-414` call `check_health()` with no timestamp). Fail-closed
      lives in the **workflow**: a query or parse that yields nothing sets `healthy=false`, which the
      existing contract already turns into preserve-and-alert
- [x] **Complete the predicate before implementing**: parseable, timezone-aware, and
      `0 <= age <= limit`. A consumer-side clock still makes a negative age possible, so an
      upper bound alone does not close the future-timestamp hole the first draft claimed it did.
      Missing, malformed or future-dated must never permit `--all`
- [x] **Three call sites, and they do not get the same policy.** `update-data.yaml:121` and
      `check-asn-drift.yaml:53` enforce recency; `check-asn-drift.yaml:83` needs the value too.
      **`tests.yaml:71-86` does not enforce it** - it runs on every PR and push to gate merges, so an
      upstream outage must not fail unrelated PRs. Its fixtures already select on file existence and
      `ASN_ARTIFACT_OPTIONAL` (`tests/conftest.py:16-24`)
- [x] Compute age **at the health check**, not frozen before the ~32-minute TLD scrape
- [x] ~~Adapt `tests/utilities/test_download.py:894`~~ **Not needed.** The field is kept, so the
      assertion passes unchanged, with its file and result assertions intact
- [~] Acceptance tests, **split by layer**. The health-check layer is fully covered; the
  **workflow layer is not**. No test executes a workflow `run:` body, so the `${result%% *}`
  split, the `"null null"` equality check and the `-z` pre-check are unverified. What is covered
  is behavioural where it could be: the `--consumed` decision moved into
  `bin/ci-record-iptoasn-fetch.py` and is unit-tested, so no shell edit can swap it. The rest is
  structural - which branch each `consumed_asn` assignment sits in, bounded by its own `fi`, and
  that the artifact-count strings are present. The string checks do **not** demonstrate the
  refusal behaves correctly. Closing this properly means lifting the remaining `run:` bodies into
  `bin/` scripts. Original intent:
  - _Health check_: zero age, exactly the limit, just over, future-dated, malformed and
    timezone-naive all decide recency. **Absent skips the check and stays healthy**, which is
    what keeps existing callers passing
  - _Workflow_: an empty or unparseable query result sets `healthy=false`, and the existing
    contract turns that into preserve-and-alert. This is the only layer where absent is fatal
  - Assert the stale path preserves and alerts, and that tests still run against preserved ASN.
    Keep all of them independent of the live artifact's real age
- [x] ~~**Removal ships separately from the gate.**~~ **Reversed - nothing is removed.** See "The field is populated, not removed" below. The deprecation-window question is moot. Original reasoning: The gate needs no schema change, and
      `metadata.json` is published and documented (`README.md:101`). Removing the writer, the
      committed key and the test is a second, announced change

## Threshold

**Settled at 40h, not the 48h this plan first proposed.** The original number was computed from the
cron schedule - producer 00:00, drift check 01:00, nightly 02:00. Those are not the times these
workflows run.

Measured over 80 scheduled runs of each, as offsets from their own cron:

| workflow          | cron  | observed offset   |
| ----------------- | ----- | ----------------- |
| `update-iptoasn`  | 00:00 | +0.57h to +10.07h |
| `check-asn-drift` | 01:00 | +4.58h to +4.96h  |
| `update-data`     | 02:00 | +0.80h to +11.74h |

Artifact age at the nightly's health check follows from those bounds:

| case                 | min age | max age |
| -------------------- | ------- | ------- |
| same-day             | -7.27h  | 13.17h  |
| yesterday's artifact | 16.73h  | 37.17h  |
| day-before artifact  | 40.73h  | 61.17h  |

The gate must accept up to **37.17h** and reject from **40.73h**, so the safe band is 37.2-40.7h.
**48h sits outside it** and accepts the 40.73h case, which is the failure the gate exists to prevent.
This plan's earlier claim that 48h "rejects two (~50.5h)" held only under a fixed delay.

**Those ages are at job start, not at the health check**, which runs after the ~32-minute scrape. Add
the time from job start to the check: about 0.53h typically, and about 2.2h on a night where every
scrape batch hits its cap. The accept edge is therefore 37.17h + that, up to roughly 39.4h, leaving
**0.6h of margin** against 40h. A scrape slower than any observed would start rejecting yesterday's
artifact. `test_yesterdays_artifact_is_accepted_on_a_slow_scrape_night` pins it.

**The one-miss/two-miss framing is wrong and has been removed.** 40.73h is the floor for consuming
the day-before-yesterday artifact, which is reached either by two failed productions **or** by one
failure plus a producer finishing at the late end of its observed range. No age threshold can
separate those, because they produce the same age. So "40h absorbs one missed production" is false:
a single miss plus a late producer is rejected, preserving and alerting. Counting productions rather
than measuring age is the only design that would make that distinction, and it is not built.

What 40h actually guarantees is narrower and still worth having: it accepts yesterday's artifact
under every observed delay and rejects anything a cycle older. The error directions are not
symmetric - too low costs one night's `--all` refresh plus a recoverable alert, too high publishes
stale labels as current - so erring low is right.

36h was rejected earlier on the grounds that it "accepts [one miss] anyway, so it does not buy the
rejection it appears to". That is true and desirable, and it was never an argument for 48h.

**The drift job's band, recorded for completeness.** It starts +4.58h to +4.96h after its 01:00 cron,
so yesterday's artifact reaches it at 19.5h to 29.4h and the day-before at 43.5h or more. 40h sits
inside that gap.

**The same-day band going negative is real, not a rounding artifact.** At -7.27h the nightly can
start before the producer has finished, so it consumes the previous day's artifact while the current
one is still uploading. A normal night can therefore present as a one-miss night, and a genuinely
negative age can only come from clock skew, which is what the 5-minute tolerance covers.

**Recheck if GitHub's scheduling delay changes materially.** The band is 3.6h wide because queue
variance is comparable to the 24h production cadence. A threshold is marginal by construction here;
the robust alternative is to count productions rather than measure age - reject when the producer has
no successful run in the last N scheduled windows, which is immune to queue delay. Not built.

## One run timestamp does not identify the bytes

This plan assumed the producer run's `updatedAt` describes the artifact the consumer downloads. It
does not, on its own. `update-iptoasn.yaml:41` names artifacts by date and both consumers use
`pattern: iptoasn-*` with `merge-multiple: true`, which is last-writer-wins on colliding filenames,
and the toolkit dedupes by artifact **name**, not run attempt. A rerun of an older successful run on
a later date therefore leaves two artifacts under one run id, and old bytes can win the extraction
while carrying a current timestamp - defeating the gate and potentially archiving live labels.

- [x] Both consumers count unexpired `iptoasn-*` artifacts on the selected run and refuse anything
      other than exactly one. In the nightly that empties the outputs and preserves; in the drift job
      it exits 1, since that job archives labels. Both queries also carry `--branch main`, since the
      gate now trusts run metadata and a `workflow_dispatch` run from any branch would satisfy it
- [x] The producer's failure path is bounded end to end, not just at the download: a 2-minute
      checkout cap, an 8-minute download cap, 1 minute each for upload and the two alerts, under
      a 14-minute job cap. The upload is capped because its stall timer resets on progress. An
      earlier 12-minute cap could be reached by a slow checkout plus a timed-out download, and a job
      cancelled at its cap runs no `failure()` step, so the outage would have been silent
- [x] `--retry-max-time 240` bounds the retry window. `--retry-delay` alone does not, because curl
      honours a server `Retry-After`, so a 503 could have waited out the step cap

## The field is populated, not removed

This plan proposed deleting `IPTOASN.last_downloaded`. That decision rested on there being no
trustworthy timestamp to write, which the gate's own work invalidates.

The name was already correct. The producer run _is_ the fetch of `https://iptoasn.com/...`
(`update-iptoasn.yaml:25`), so its run timestamp records the same fact every other entry records:
when the data now in hand was obtained upstream. Only the observer differs.

Keeping it removes work rather than adding it - no rename, no schema change, no `README.md:101`
rewrite for that field, and no deprecation window.

- [x] `last_checked` moves on every night an artifact was pulled; `last_downloaded` and `run_id` move
      only when the build consumed it. This is the convention the file already follows, which
      `ROOT_ZONE_DB` demonstrates by sitting ten months stale against a nightly `last_checked`. A
      preserve night is iptoasn's 304
- [x] `bin/ci-record-iptoasn-fetch` owns the write, gated on `steps.build.outputs.consumed_asn`. It
      cannot live in the build: `test_build_does_not_rewrite_iptoasn_metadata` pins that boundary
- [x] The step runs before `bin/test`, so the tree that ships is the tree that was tested
- [x] A direct `--download-iptoasn` clears `run_id`: bytes from upstream are not attributable to a
      producer run. Merging it forward would pair a local fetch time with an unrelated CI run
- [x] `run_id` documented at `README.md:101`, since it is not an http-fetch lifecycle field

## Deferred, recorded not built

Two left; the producer timeout below shipped with this plan.

- **Content hash beside `run_id`.** The only thing that would catch upstream serving a stale dataset
  with a fresh run timestamp, which this plan concedes the run-recency gate cannot detect. One
  `sha256sum` in a step already reading the file. Left out to keep the schema change minimal.
- [x] ~~**The producer's `curl` has no `--max-time` and its step no `timeout-minutes`.**~~ **Done.**
      `--max-time 120 --retry 2 --retry-max-time 240`, a step cap of 8 minutes, and an explicit job cap of 14 - the job had
      none, which meant `TestTimeoutBudgets` skipped it entirely. A stalled fetch can no longer end
      the job before its `failure()` alert runs.
- **`update-iptoasn.yaml` uses floating action tags and carries no `permissions:` block** while every
  other workflow pins SHAs and starts from `permissions: {}`. Its run metadata is now a gate input,
  which raises the stakes on hardening it.

## Open questions

- **Use `updatedAt`. Shipped without the `createdAt` fallback and without `// empty`**: the
  implementation uses a single `\(.databaseId) \(.updatedAt)` render plus a `run_id = updated_at`
  equality check, which catches jq rendering an empty array as `"null null"`. Original reasoning: A re-run of the producer re-fetches and
  re-uploads, so `updatedAt` tracks when the artifact in hand was actually produced while
  `createdAt` is frozen at the original run's start. At the 40h threshold the few minutes between
  them are irrelevant; the re-run case is not. Parse defensively
  (`jq -r '.[0].updatedAt // empty'`) so no successful run yields an empty string rather than the
  literal `null`.
- ~~Whether the separate removal change needs a deprecation window.~~ Moot: nothing is removed.

## Noted, outside this plan

- ~~The producer's `curl` has no maximum duration and its step no timeout.~~ Fixed in this plan; see
  the Deferred section's first item, which shipped.
