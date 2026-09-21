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
But 45-day artifact expiry is **not** a backstop on published ASN age: preserve mode copies
committed values indefinitely (`src/build/tlds.py:706-728`), and after recovery `--all` still needs
a source change or `repairable_damage`, which counts only `"Unknown"` labels
(`bin/check-asn-drift.py:125-134`). Stale-but-plausible enrichment can therefore outlive the outage.

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

**One test reads it**, and `bin/test` gates the nightly patch (`update-data.yaml:321`), so removal
has to account for it:

- `tests/utilities/test_download.py:894` asserts the field exists after a download. This is the
  only adaptation removal requires.
- `tests/build/test_tlds.py:489` writes its **own** sentinel to a temp path and compares that
  (`:493`, `:505`). It never reads the published field and is unaffected. The first draft's
  earlier draft of this plan wrongly listed it.

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

- [ ] Add the timestamp to the run query and pass it to the health check as
      `--artifact-created-at`. **Absent means the recency check does not run**, which keeps the
      existing health tests and local runs working unchanged
      (`tests/test_check_asn_drift.py:388-414` call `check_health()` with no timestamp). Fail-closed
      lives in the **workflow**: a query or parse that yields nothing sets `healthy=false`, which the
      existing contract already turns into preserve-and-alert
- [ ] **Complete the predicate before implementing**: parseable, timezone-aware, and
      `0 <= age <= limit`. A consumer-side clock still makes a negative age possible, so an
      upper bound alone does not close the future-timestamp hole the first draft claimed it did.
      Missing, malformed or future-dated must never permit `--all`
- [ ] **Three call sites, and they do not get the same policy.** `update-data.yaml:121` and
      `check-asn-drift.yaml:53` enforce recency; `check-asn-drift.yaml:83` needs the value too.
      **`tests.yaml:71-86` does not enforce it** - it runs on every PR and push to gate merges, so an
      upstream outage must not fail unrelated PRs. Its fixtures already select on file existence and
      `ASN_ARTIFACT_OPTIONAL` (`tests/conftest.py:16-24`)
- [ ] Compute age **at the health check**, not frozen before the ~32-minute TLD scrape
- [ ] Adapt `tests/utilities/test_download.py:894` only, keeping its file and result assertions
- [ ] Acceptance tests, **split by layer**, because the two layers answer "absent" differently:
      - *Health check*: zero age, exactly the limit, just over, future-dated, malformed and
        timezone-naive all decide recency. **Absent skips the check and stays healthy**, which is
        what keeps existing callers passing
      - *Workflow*: an empty or unparseable query result sets `healthy=false`, and the existing
        contract turns that into preserve-and-alert. This is the only layer where absent is fatal
      - Assert the stale path preserves and alerts, and that tests still run against preserved ASN.
        Keep all of them independent of the live artifact's real age
- [ ] **Removal ships separately from the gate.** The gate needs no schema change, and
      `metadata.json` is published and documented (`README.md:101`). Removing the writer, the
      committed key and the test is a second, announced change

## Threshold

Producer 00:00 UTC, drift check 01:00, nightly **02:00** (`update-data.yaml:6`). Observed commit
times of 07:00-14:19 are execution delay, not schedule.

**Settled at 48h.** 36h was considered and rejected: at a 02:00 consumption a single missed
production is only ~26h old, which 36h accepts anyway, so it does not buy the rejection it appears
to. The two values differ only between 36h and 48h, which is delayed-consumption territory rather
than a missed cycle. 48h absorbs one missed production under observed queue delay and rejects two
(~50.5h).

This is an operational tolerance, not a measured guarantee. Log the observed age, run id and verdict
from day one and refine from data - but ship the number rather than let measurement postpone the
gate.

## Open questions

- **Use `updatedAt`, falling back to `createdAt`.** A re-run of the producer re-fetches and
  re-uploads, so `updatedAt` tracks when the artifact in hand was actually produced while
  `createdAt` is frozen at the original run's start. At a 48h threshold the few minutes between
  them are irrelevant; the re-run case is not. Parse defensively
  (`jq -r '.[0].updatedAt // empty'`) so no successful run yields an empty string rather than the
  literal `null`.
- Whether the separate removal change needs a deprecation window or an announcement suffices.

## Noted, outside this plan

- The producer's `curl` has no maximum duration and its step no timeout, on a `ubuntu-slim` runner
  capped at 15 minutes (`update-iptoasn.yaml:16,26`). A stalled fetch can terminate the job before the
  `failure()` notification steps run, so "producer failures already alert" has a hole.
