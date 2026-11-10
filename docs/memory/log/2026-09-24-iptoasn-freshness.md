---
title: The ASN health gate gained a recency check, and IPTOASN metadata stopped lying
summary: A stale-but-healthy artifact could publish month-old labels as current. The gate now rejects an artifact older than 40h, a threshold derived from 80 nights of observed queue delay rather than the cron schedule. IPTOASN.last_downloaded keeps its name and finally follows this file's own convention.
created: 2026-09-24
author: Eric Case
tags: [log, decision, ci, asn, iptoasn, metadata, freshness]
---

# 2026-09-24 - iptoasn freshness

Follows [the freshness plan](../../plans/current/2026-09-21-iptoasn-freshness.md).

## The gate asked whether the artifact was good, never whether it was recent

Artifacts live 45 days, and the consumer took the newest successful producer run with no age check.
A prolonged producer outage therefore left a healthy-looking artifact eligible, and its labels
published as current enrichment. `artifact_age_problem` in `src/analyze/asn_health.py` now answers
recency; `max_age_hours` sits on `Thresholds` beside every other boundary.

An absent `--artifact-created-at` **skips** the check, which keeps local runs and `tests.yaml`
working. An empty string is a failure, not a skip. Fail-closed therefore lives in the workflows: the
nightly sets `healthy=false` without invoking the checker, and the drift job exits 1, because that
job archives labels and a stale artifact it cannot date would propose archiving live ones.

`now` is a parameter, not `datetime.now()` read internally. Without it the "exactly at the ceiling"
case races the evaluation instant and is flaky by construction.

## 40 hours, not 48

The plan's 48h came from the cron schedule. Observed offsets over 80 runs are much larger: the
producer is ready +0.57h to +10.07h after its 00:00 cron, and the nightly starts +0.80h to +11.74h
after its 02:00. Yesterday's artifact therefore reaches the nightly at up to 37.2h, and the
day-before at 40.7h or more. 48h accepts that 40.7h case, which is the thing the gate exists to stop.

**What 40h guarantees is narrower than "absorbs one missed production", and that phrasing was wrong.**
40.7h is reached either by two failed productions or by one failure plus a producer finishing at the
late end of its range. No age threshold separates those, since the age is identical. So a single miss
plus a late producer is rejected, preserving and alerting. The real guarantee is: accept yesterday's
artifact under every observed delay, reject anything a cycle older. Counting productions instead of
measuring age is the only design that would distinguish them, and it is not built.

Those ages are at job start. The health check runs after the ~32-minute scrape, which adds about
0.53h normally and about 2.2h if every scrape batch caps out, so the accept edge reaches ~39.4h and
leaves **0.6h of margin**. A slower scrape than any observed would start rejecting yesterday's
artifact. Erring low is still right: too low costs one night's refresh and a recoverable alert, too
high ships stale data as current.

Recheck if GitHub's scheduling delay changes materially. The usable band is thin because queue
variance is comparable to the 24h production cadence.

## One run timestamp does not identify the bytes

The producer names artifacts by date and both consumers use `pattern: iptoasn-*` with
`merge-multiple: true`, which is last-writer-wins. A rerun of an older run on a later date leaves two
artifacts under one run id, so old bytes can win the extraction while carrying a current timestamp.
Both consumers now count unexpired `iptoasn-*` artifacts on the selected run and refuse anything but
exactly one, and both queries carry `--branch main` because the gate trusts run metadata.

A cheaper design exists and is not built: the same API call returns each artifact's name, which the
producer sets to `iptoasn-YYYY-MM-DD`. Comparing that date to the consumer's own UTC date counts
productions directly, with roughly 12h of headroom instead of 0.6h, and takes the timestamp from the
bytes rather than the run record. Worth revisiting if the margin ever bites.

## last_downloaded keeps its name

Removal was the plan's answer when the only candidate timestamp was the gzip mtime. With a
server-generated producer-run timestamp the field can simply become true, and the name was already
right: the producer run _is_ the fetch from iptoasn.com, so the recorded fact matches every other
entry in the file.

It now follows this file's existing convention, that `last_downloaded` moves only when content
reached the published data - the rule `ROOT_ZONE_DB` already demonstrates by sitting ten months stale
against a nightly `last_checked`. A preserve night is iptoasn's 304: `last_checked` advances,
`last_downloaded` does not. During an outage the download date visibly stops, which is the diagnostic.

`run_id` is new beside it, for tracing a verdict to its artifact. A direct `--download-iptoasn`
clears it, since bytes fetched from upstream are not attributable to a producer run.

`bin/ci-record-iptoasn-fetch` owns the write, gated on the build having consumed the artifact.
`last_checked` is stamped when that step runs, up to about two hours after the download; daily
granularity is all it is for. The step exits non-zero if the entry did not reach disk, because
`save_metadata` only logs a failed write.
It cannot live in the build: `test_build_does_not_rewrite_iptoasn_metadata` pins that boundary.

## Action pins match across workflows

The producer's run metadata is now a gate input, so `update-iptoasn.yaml` and `tests.yaml` pin every
action to a full SHA, the same one the other workflows use, and the producer starts from
`permissions: {}`. `jactionlint` fails on a tag pin and `TestActionPins` on one action pinned to two SHAs, which keeps
the Dependabot `github-actions` group bumping them together. `workflows-disabled/` is out of scope:
nothing runs it and Dependabot does not scan it.
