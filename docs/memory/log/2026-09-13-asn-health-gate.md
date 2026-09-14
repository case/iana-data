---
title: The ASN health gate picks the build mode instead of blocking
summary: A bad iptoasn artifact used to reach the build and emit Unknown everywhere, which M1 turned from a failure into a silent warning. The gate now downgrades --all to --preserve-asn and alerts, so the nightly never breaks on bad input. Six tripwires, measured against nine snapshots.
created: 2026-09-13
author: Eric Case
tags: [log, decision, ci, asn, drift, iptoasn]
---

# 2026-09-13 - the ASN health gate

M3 of [the ASN drift plan](../../plans/current/2026-09-11-asn-drift-automation.md).

## Downgrade, never block

`update-data.yaml` already picked `--all` on an IANA source change and `--preserve-asn` otherwise.
The gate now adds a condition: `--all` needs a *healthy* artifact. Anything else preserves committed
ASN and fires a Pushover alert. Only an explicit healthy result permits a refresh, so a failed check,
a missing output or a timeout all preserve.

That is the whole design. Blocking was the failure mode being removed: a broken nightly stays broken
until someone has time, while preserved ASN costs nothing a normal night does not already cost.

**It also makes the thresholds easy.** A false positive costs one night of preserved ASN, so the
numbers sit just outside observed variance instead of being defended as calibrated limits.

## The six signals

Per address family: non-zero-ASN coverage, useful-label coverage, and address count; plus the
artifact's usable-record count. Measured over nine committed `tlds.json` snapshots,
2026-07-01 to 2026-09-11: IPv4 coverage 99.9566-99.9783%, IPv6 99.7696-99.8158%, addresses
4,600-4,612 and 4,333-4,345, 386-393 distinct labels, 718,331 rows.

Two traps worth keeping:

- **`asn == 0` carries `as_org: "Not routed"`, not `"Unknown"`.** Counting `"Unknown"` reports 100%
  coverage and hides the real figure. The first draft of this gate did exactly that, and its 99.9%
  floor would have rejected the healthy IPv6 baseline.
- **Label cardinality is not label coverage.** A floor of 300 distinct labels permits dropping the
  86 most-used ones, which strips the label from 8,332 of 8,941 addresses while every other signal
  passes. Coverage is per address.

Coverage does not subsume the record floor either: two ranges spanning all of v4 and v6 give 100%
coverage from two records.

## One parser

The build used `line.strip()` and the detector `rstrip("\n")`. For a row with an empty trailing org
field that is four columns versus five, so the gate counted 718,331 usable records for an artifact
the build would discard entirely. `parse_gzipped_iptoasn` in `src/parse/iptoasn.py` is now the single
definition and the build delegates to it.

It also validates range endpoints. `ASNLookup.lookup` parsed `end_ip` outside its `try`, so one
malformed endpoint raised `AddressValueError` mid-build - invisible to any probe that never selected
that range.

## The guard M1 kept had to go

`_require_iptoasn_source` failed CI on a missing artifact, and `bin/test` gates the commit step. So a
failed download blocked the nightly even after the gate had already chosen the safe build. It now
returns a bool, and `ASN_ARTIFACT_OPTIONAL` - set by the nightly when the gate rejected the artifact -
selects a preserve build for the fixtures instead. The structural, foreign-key and IANA/ICANN
assertions still run, against the preserved graph; only the fresh-ASN enrichment is unavailable.

**The opt-out outranks the file existing.** Checking existence alone would reread an artifact the
gate had already rejected.

## Recovery is netted and deduplicated

A preserve build copies committed values forward, so an `Unknown` landed during fallback persists
until the next `--all`. The gate forces one when the artifact can repair it. Two corrections that
mattered: count only damage *this artifact* repairs, or a permanently unroutable address latches the
trigger on forever; and net repairs against newly-broken addresses, deduplicated by address, or
alternating artifacts oscillate and one address serving 125 nameservers outvotes 100 others.

## Deferred

Freshness has no threshold: one gzip header is not an upstream convention and `now - mtime <= limit`
accepts a future timestamp. Label correctness is out of scope - a permutation of operator names
defeats all six signals and needs an independent reference.
