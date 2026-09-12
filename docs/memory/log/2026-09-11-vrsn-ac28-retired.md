---
title: VRSN-AC28 left iptoasn and HGTLD returned; the Verisign label pair is flapping, not migrating
summary: AS397198/397200/397204 labeled VRSN-AC28 vanished from the iptoasn table and the same four /24s went back to AS36623/HGTLD, reversing the 2026-08-18 change. Fix is data - retire VRSN-AC28 to aliases. Third occurrence in three months; the durable options are recorded here.
created: 2026-09-11
author: Eric Case
tags: [log, decision, manual-data, organizations, asn, drift, verisign]
---

# 2026-09-11 - VRSN-AC28 retired, and the label pair is flapping

`test_source_names_appear_in_raw_data` failed with `verisign / asn / 'VRSN-AC28' - no raw match`, nearest existing `VRSN-AC50-340`. Surfaced on PR #117, a dependabot `uv.lock` bump that touches no data - the suite rebuilds from the latest `update-iptoasn` artifact, so the failure reaches every open PR and `main` alike.

This is the reverse of [2026-08-18 hgtld-retired](2026-08-18-hgtld-retired.md), on the same four prefixes.

| | ASN | `as_org` string |
|---|---|---|
| 2026-07-15 snapshot | 36623 | `HGTLD` |
| 2026-08-18 CI artifact | 397200 | `VRSN-AC28` |
| 2026-09-11 live table | 36623 | `HGTLD` |

`192.41.162.0/24`, `192.48.79.0/24`, `192.52.178.0/24`, `192.55.83.0/24` moved back. `VRSN-AC28` now returns 0 rows; AS397198/397200/397204 are absent entirely. The pair is oscillating between two labels for one set of prefixes, so treat neither as the stable one.

## Fix

`VRSN-AC28` moved from `verisign.source_names.asn` to `aliases`. `HGTLD` stays in `aliases` despite being live again: promoting it back only re-arms the same failure on the next flip, and it resolves identically where it is. `VRSN-AC50-340` remains the sole `asn` seed and carries the attribution, unchanged.

An audit of all 73 remaining `source_names.asn` strings against the live table found `VRSN-AC28` the only casualty.

## Why aliases lose nothing

`build_resolver` in `src/parse/organizations.py` indexes `[*source_names[bucket], *display_name, *aliases]` into every bucket, and it is the only consumer of `source_names`. So for resolution, a label in `aliases` and a label in `source_names.asn` are the same thing. The sole difference is that `source_names` is policed by `test_source_names_appear_in_raw_data` and `aliases` is not. HGTLD sat in `aliases` for three weeks with attribution intact, which is the empirical proof.

## Durable options, not yet chosen

The assertion treats three buckets alike, but they are not alike. `iana` and `icann` strings are curated registry names where a mismatch really is a typo. `asn` strings are opaque third-party labels from a derived dataset that has now flapped three times in three months ([2026-07-16](2026-07-16-teleinfo-asn-rename.md), [2026-08-18](2026-08-18-hgtld-retired.md), this entry). For the `asn` bucket the assertion tests upstream stability that upstream does not offer, and because `update-data.yaml:303` gates the commit step on `run-tests.outcome == 'success'`, each flap stops the nightly refresh until a human edits the seed. That cost a week of stale data in August.

1. **Warn instead of fail for the `asn` bucket**, keeping the hard assertion for `iana`/`icann`. Smallest change, ends the nightly-blocking failure, gives up little because aliases resolve identically.
2. **Auto-retire drifted `asn` labels through the existing drift-PR machinery** (`bin/ci-open-drift-pr`, `check-coordinates.yaml`). Keeps the invariant and unblocks the nightly, at the cost of another workflow on a path whose sharp edges [2026-09-09](2026-09-09-coordinate-drift-pr.md) documents.
3. **Collapse `source_names.asn` into `aliases`** and stop curating iptoasn labels as identity. Which label is current is already derivable from `tlds.json`.

## Known and accepted

- Reproduced against `iptoasn.com` live-latest, not CI's pinned artifact, which [2026-07-16](2026-07-16-teleinfo-asn-rename.md) warns against: `gh run download` on the artifact returns HTTP 401 under the current token. The absence of `VRSN-AC28` is corroborated by CI's own failure output, but the HGTLD return is a live-latest observation and may sit ahead of the artifact.
