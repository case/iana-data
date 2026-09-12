---
title: The archived bucket - source-scoped retirement for curated names
summary: Retired ASN labels were parked in aliases, which resolve in all three buckets, so retirement widened them instead of narrowing. archived.<source> resolves in that source only and is never asserted. Six labels left aliases - five archived, HGTLD reseeded because it is live.
created: 2026-09-12
author: Eric Case
tags: [log, decision, manual-data, organizations, asn, drift, schema]
---

# 2026-09-12 - the `archived` bucket

M2 of [the ASN drift plan](../../plans/current/2026-09-11-asn-drift-automation.md).

## Why not `aliases`

Three retirements parked a departed `as_org` label in `aliases`. But `build_resolver` indexes
`[*source_names[bucket], *display_name, *aliases]` into **every** bucket, so retiring an opaque
iptoasn token there also declares it a valid IANA and ICANN name. Retirement was widening.

```json
"source_names": { "asn": ["VRSN-AC50-340"] },
"archived":     { "asn": [{ "name": "VRSN-AC28", "archived_on": "2026-09-12" }] }
```

`archived.<source>` resolves in that source only, is never asserted against raw data, and is absent
when empty. `archived_on` is required and is the date it was archived, not a last-seen date: the
snapshot revealing an absence is by definition one where the label has gone. Entries are never
promoted back out.

## The split

Five labels had no raw match and went to `archived.asn`: verisign (`VERISIGN-AS`, `VGRS-AC25`,
`VRSN-AC28`), cloudflare (`CLOUDFLARENET`), teleinfo (`CAICTNET ...`). `HGTLD` went to
`source_names.asn`, because counted against the pinned artifact it is live on `com`, `edu`, `net` -
closing the open caveat in [2026-09-11](2026-09-11-vrsn-ac28-retired.md). That is not an archive
promotion: relative to `main` it sat in `aliases`. It buys no attribution, its TLDs being a subset
of `VRSN-AC50-340`'s 20; it is seeded so the drift automation sees a live label, because M4 never
moves an entry out of `archived`.

Both destinations are asn-scoped, so all six narrow identically.
`tests/parse/test_organizations_archive_migration.py` pins the complete before/after
`(source, name) -> slug` diff at exactly 12 removals: 6 labels x the `iana` and `icann` buckets.

## No test may assert an ASN label is live

The integrity fixture rebuilds ASN from the current artifact, so an assertion that `HGTLD` appears
in raw data fails hard on the next flip and `update-data.yaml:303` stops the nightly commit - which
is what M1 removed. Seed-shape guards pin which field a label occupies; liveness belongs to
`test_source_names_appear_in_raw_data`, which warns.

## Validation

`validate_organizations` reports and never raises, matching `build_resolver`'s collisions; a test
asserts the committed seed is clean. `archived_on` needs `^\d{4}-\d{2}-\d{2}$` **and**
`date.fromisoformat`, since the regex accepts `2026-13-45` and `fromisoformat` accepts `20260912`. A
shape-invalid entry contributes no resolution key and no drift evidence, or `{"name": "GONE"}` would
buy a relaxed assertion. Overlap with `display_name` is allowed: `nic-chile` seeds its own.

## Why `data/generated/organizations.json` is regenerated here

`update-data.yaml` adopts `data/manual/` from current `main` mid-run while `sync` keeps the job's own
`src/`, so an in-flight run can pair the old resolver with the migrated seed. Measured, that loses
**zero** attributions - every affected TLD carries a live sibling label. Regenerating is still right:
`sync` passes `--guard data/generated/` and declines adoption when a guarded path moved, so such a
run keeps old code *and* old seed. Merge count is irrelevant - `ci-land-data-patch:145` diffs the
checkout against the fetched tip - so only moving a guarded path matters.
