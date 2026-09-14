# ASN label drift: an archive bucket, and automation to maintain it

## Problem

`data/manual/organizations.json` seeds each org with `source_names` in three buckets: `iana`, `icann`, `asn`. The `asn` strings are opaque `as_org` labels from iptoasn, a third-party derived dataset.

`test_source_names_appear_in_raw_data` asserts every `source_names` string occurs as a raw value in a freshly built `tlds.json`. It has fired three times in three months ([2026-07-16](../../memory/log/2026-07-16-teleinfo-asn-rename.md), [2026-08-18](../../memory/log/2026-08-18-hgtld-retired.md), [2026-09-11](../../memory/log/2026-09-11-vrsn-ac28-retired.md)). The last two are the same four /24s oscillating between `HGTLD` and `VRSN-AC28`: a flap, not a migration.

`update-data.yaml:303` gates the nightly commit on tests passing, so each flap stops the data refresh until a human edits the seed. In August that was seven consecutive nights with no data landing.

## Approach

A schema change, automation that maintains it, and a tolerance for the window between them.

### The `archived` bucket

```json
"source_names": { "asn": ["VRSN-AC50-340"] },
"archived":     { "asn": [{ "name": "VRSN-AC28", "archived_on": "2026-09-11" }] },
"aliases":      ["VGRS-AC25"]
```

- **`source_names.<bucket>`** - asserted present in raw data.
- **`archived.<bucket>`** - previously curated for that source and no longer matching raw data. Still resolves, **in that bucket only**. Never asserted. Not proof of observation: a mistyped label that never matched would be archived the same way.
- **`aliases`** - alternate names resolving across all buckets, as today.

`archived` over `retired` or `unmatched`: we observe absence from one snapshot, never upstream's intent. `retired` claims someone else's decision; `unmatched` was already false for `HGTLD` within three weeks.

**`archived_on` is the date the entry was written into the archive.** Not "last seen": the detector's snapshot is by definition the one where the label has gone, so absence cannot date a presence. It is never rewritten once set. It does **not** bound true last-seen: a pending PR, a stale artifact, a migrated entry, or a label returning after archival all break that inference.

**Entries stay archived.** Moving one back into `source_names` re-arms the drift report on the next flip. Deletion is a human decision.

### Assertion policy, stated once

| Bucket          | `source_names` mismatch | Live-data assertion that fails only because an `asn` label is gone |
| --------------- | ----------------------- | ------------------------------------------------------------------ |
| `iana`, `icann` | **fail**                | **fail**                                                            |
| `asn`           | **warn**                | **warn**                                                            |

The `asn` warn is permanent, not window-scoped, and archive state plays no part in deciding it.

## Deploy milestones

Four independently deployable steps, in dependency order. Each is a separate reviewed change; none assumes the next one lands.

| Milestone                     | Delivers                                    | Depends on |
| ----------------------------- | ------------------------------------------- | ---------- |
| **M1** Stop the nightly blocking | Data refresh survives an `asn` flap       | -          |
| **M2** The `archived` bucket  | Honest schema for labels upstream dropped   | M1         |
| **M3** Health gate + detector | Nightly survives a bad artifact; drift detectable | M2       |
| **M4** Archival automation    | Drift proposes its own fix as a PR           | M3         |

M1 is the whole of the urgent problem. M2 is data modelling. M3 keeps the nightly moving when the ASN artifact is bad and builds the detector; M4 turns drift into a PR. M4 is the only one needing **write** credentials - M3 uses the existing Pushover secrets.

---

## M1: stop the nightly blocking — **DONE**

Test-only. No schema change, no new files, no CI change. Manual archival stays the fallback, as used for `VRSN-AC28`.

**Four** live-data assertions block the nightly, not one:

| Test                                                  | Currently asserts                          |
| ----------------------------------------------------- | ------------------------------------------ |
| `test_source_names_appear_in_raw_data:224`            | every `source_names` string matches raw data |
| `test_every_org_has_at_least_one_role:98`             | no org has zero roles                       |
| `test_uk_nameservers_span_distinct_operators:274`     | `{nominet, ultradns} <= .uk as_org_slugs`   |
| `test_knipp_spans_iana_tech_and_asn_operator:281`     | `knipp-medien` holds an `asn.operator` role |

The last two encode real invariants using live orgs as the example, so an ASN label drift breaks them for a reason unrelated to what they test.

**One rule, applied to all four: a failure explainable by an absent `asn` label, and only by that, warns; everything else fails.**

The condition is **observable, not causal**. The graph cannot tell upstream drift from damaged input or broken enrichment, and no milestone here proves which it was. What the helper checks is narrower and decidable: whether any of the org's resolution keys still matches raw data.

- [x] Shared helper, so the four callers cannot drift apart. It needs the org's **complete** resolution keys - `source_names` in all three buckets plus `display_name` and `aliases`, all of which `build_resolver` (`src/parse/organizations.py:74`) indexes - and the raw values in the assertion's own scope (`.uk` for the uk test, all TLDs for an ASN operator role)
- [x] **A live matching key with a missing relationship fails**, even when another key of the same org is absent. That is a build defect, not drift
- [x] `test_source_names_appear_in_raw_data`: `iana`/`icann` fail, `asn` warns, keeping `_diagnose_unmatched`'s nearest-match output
- [x] `test_every_org_has_at_least_one_role`: warns only when the org has at least one `asn` entry, no key matches in any bucket, and no unmatched key is `iana`/`icann`
- [x] **Empty `source_names` fails, not warns** - both `{}` and `{"asn": []}`, so the rule is not vacuously true
- [x] `test_uk_nameservers_span_distinct_operators` and `test_knipp_spans_iana_tech_and_asn_operator`: both index into optional structure (`as_org_slugs`, `roles["asn"]["operator"]`), so a disappearance raises `KeyError` before any helper runs. Handle the absent key first
- [x] Warnings use `warnings.warn`, not `logging`. There are no warning filters and `addopts` (`pyproject.toml:31`) sets none, so pytest's summary shows them; a log line on a passing test would be captured and lost
- [x] Fixtures drive **all four caller paths** with synthetic graphs, not just the helper: absent optional keys; a live fallback name with a missing relationship; concurrent `asn` drift *and* a genuine `iana` failure; both empty-source forms. Assert both the warnings and the retained hard failures
- [x] Do **not** verify against today's seed with `VRSN-AC28` removed. It already sits in `aliases` with only `VRSN-AC50-340` under `source_names.asn`, so that exercises nothing. Use a fixture carrying the earlier active seed
- [x] `README.md:300` ("no record is ever orphaned") and `:306` (every org carries `roles`) are corrected **here**, not deferred. M1 makes both false, and deferring leaves the repo inconsistent if M2 never lands

**Manual archival does not generalise, and M1 says so** in `_DRIFT_ADVICE`. `ultradns` carries `source_names.asn = ["SECURITYSERVICES"]` and nothing else (`data/manual/organizations.json:1010`). If that label drifts, M1 warns - but moving it to `aliases` the way `VRSN-AC28` was moved leaves empty `source_names`, which M1 deliberately fails. For an `asn`-only org the maintainer must keep the absent seed in place, reseed the org, or remove the record deliberately. **Superseded by M2**: the label moves to `archived.asn`, which keeps resolving it in the `asn` bucket and counts as `asn` evidence, so an archived-only org warns rather than failing.

**Known limitation, accepted:** typo detection for `asn` is given up. A mistyped label never matches and now only warns.

**What M1 costs while M3 does not exist.** A corrupt gzip makes the build emit `as_org: "Unknown"` throughout; after M1 the resulting missing relationships warn instead of failing, and round-trip checks still pass because they compare data generated from the same snapshot. Three qualifications:

- A **missing** file still fails CI via `_require_iptoasn_source`. Keep that guard. **Superseded by M3**: that guard is what makes a failed artifact download block the nightly, which is the outcome M3 exists to prevent. M3 splits it - see "The guard M1 kept" there.
- Degraded published ASN data persists through later `--preserve-asn` builds even after the artifact recovers (`update-data.yaml:252-264`).
- A warning does not fire `update-data.yaml`'s test-failure notification, so the alert is lost too, not just the gate.

This trades a blocking data-quality safeguard and its alert for CI-log diagnostics, indefinitely, unless M3 lands. Accepted deliberately as the price of availability - and it is why M3 is not merely convenience.

---

## M2: the `archived` bucket - **DONE**

- [x] Schema: source-scoped `archived`, entries `{name, archived_on}`
- [x] `build_resolver` (`src/parse/organizations.py:74`) indexes `archived[source]` into that source **only**
- [x] Validation in `parse_organizations_manual`: recognized buckets, non-empty names, `YYYY-MM-DD` dates, no duplicates, no name in both `source_names` and `archived` for one bucket. It currently validates only that the document is a list (`:36`)
- [x] Decide and test whether `archived_on` is required or optional - M2 and the migration must agree. **Required**: the writer always knows the date, M4 always sets it, and an optional field invites dateless entries with nothing to backfill from
- [x] Tests: an archived label resolves in its own bucket and **not** in the other two

### Migrating the existing graveyard

`aliases` already holds retired ASN labels by design - `2026-07-16-teleinfo-asn-rename.md:22` names `verisign -> VGRS-AC25` and `cloudflare -> CLOUDFLARENET`. Moving them **narrows** resolution, because aliases resolve in all three buckets today.

- [x] Evidenced inventory from the memory log, not inferred from present liveness
- [x] Acceptance test compares the **complete** before/after `(source, name) -> slug` mapping, with an explicit allowlist of justified removals. Iterating current raw values is insufficient: it cannot see a key that no live string exercises
- [x] Separately, assert no currently-resolving raw value changes slug
- [x] `archived_on` for migrated entries is the migration date, since that is what the field means. Historical retirement dates belong in the memory log, not here

---

## M3: health gate and detector - **DONE**

**Revised 2026-09-12.** The original M3 was a report-only CI step. Two things changed it: the
maintenance goal is that the nightly never breaks and drift arrives as a mergeable PR, not as CI
logs someone has to read; and an unhealthy artifact has a better response than either blocking or
reporting.

### The gate picks the build mode; it never blocks

`update-data.yaml:253-265` already runs `--all` on an IANA source change and `--preserve-asn`
otherwise, and `_asn_lookup_from_committed` (`src/build/tlds.py:707`) reproduces committed ASN
exactly. So an unhealthy artifact downgrades `--all` to `--preserve-asn` and fires a Pushover
alert. The nightly completes, IANA changes publish, ASN keeps its last known good values, and
degraded data never lands.

This also pays off M1's admitted debt: M1 gave up the blocking safeguard **and its alert**, since a
warning fires no notification. The alert comes back here without re-arming the flap.

**The cheap consequence is what makes the thresholds easy.** A false positive costs one night of
preserved ASN, which is what every non-source-change night already does. So thresholds sit tight
against observed values rather than loose. They are tripwires for catastrophic loss, documented as
that, not as statistically calibrated limits.

**Accepted cost:** on a source-change night that falls back, a brand-new TLD's nameservers are
absent from the committed lookup, so that TLD alone carries `as_org: "Unknown"` until the artifact
recovers. Bounded and self-healing.

### Measured baseline

Nine committed `data/generated/tlds.json` snapshots, 2026-07-01 to 2026-09-11, deduplicated
addresses, predicate `asn != 0`:

| signal | observed range |
| --- | --- |
| IPv4 non-zero-ASN coverage | 99.9566 - 99.9783% (1-2 unrouted of ~4,610) |
| IPv6 non-zero-ASN coverage | 99.7696 - 99.8158% (8-10 unrouted of ~4,340) |
| distinct `as_org` labels | 386 - 393 |
| distinct addresses | IPv4 4,600-4,612, IPv6 4,333-4,345 |
| artifact rows (one sample) | 718,331, all parseable |

`asn == 0` records carry `as_org: "Not routed"`, **not** `"Unknown"`; only a lookup miss yields
`"Unknown"`. Counting the wrong one reports 100% coverage and hides the real figure.

### The guard M1 kept

`_require_iptoasn_source` (`tests/integration/test_organizations_integrity.py:42`) calls
`pytest.fail` when the artifact is absent in CI. `bin/test` runs that suite and
`update-data.yaml:303` gates the commit on it, so **a failed artifact download blocks the nightly
even after the health gate has already chosen the safe build**. M1 kept that guard deliberately;
M3 reverses it, because it conflates two different things.

- [x] Tests asserting the **health module classifies correctly** keep blocking. They catch
      implementation regressions, which is what a test is for
- [x] A test asserting **tonight's artifact is healthy** must not block. That is an input problem
      the fallback already handles
- [x] Structural, resolver, and `iana`/`icann` assertions stay hard, unchanged from M1
- [x] The integration fixtures must honour the selected build mode. Passing `preserve_asn=True` to
      the current temp builds is **not** sufficient: their temp `tlds.json` holds no committed
      baseline to preserve from

### Thresholds

Inclusive boundaries, measured over the nine snapshots above.

| signal | population | observed | fails when |
| --- | --- | --- | --- |
| IPv4 unrouted (`asn == 0`) | distinct v4 addresses | 1-2 of ~4,610 | above 25 |
| IPv6 unrouted (`asn == 0`) | distinct v6 addresses | 8-10 of ~4,340 | above 60 |
| IPv4 useful-label coverage | distinct v4 addresses | 99.9783% | below 95% |
| IPv6 useful-label coverage | distinct v6 addresses | 99.8158% | below 95% |
| IPv4 distinct addresses | built graph | 4,600-4,612 | below 4,000 |
| IPv6 distinct addresses | built graph | 4,333-4,345 | below 3,800 |
| artifact parseable rows | the gzip | 718,331 (one sample) | below 500,000 |

**Useful-label coverage is a separate signal from unrouted count, and label cardinality is not a
substitute for either.** A cardinality floor of 300 would permit dropping the 86 most-used labels,
which strips the label from 8,332 of 8,941 addresses - 93.2% - while every other threshold passes.
Measured, not hypothetical. Cardinality may stay as a secondary signal; it must not be relied on.
The two coverage signals coincide on today's data because every sentinel label sits on an
`asn == 0` record, but an `asn != 0` record labelled `Unknown` separates them, and that is the
attack.

Record counts and label coverage are anchored to a single measured artifact until more are sampled.

### Checklist

- [x] `src/analyze/asn_health.py`: pure functions over an address set plus an `ASNLookup`. No full
      build - the gate looks up an address set against the new artifact, so it runs before the build
- [x] **Probe both address sets.** The committed `tlds.json` population is a stable baseline but is
      *last night's*; an artifact can cover it perfectly and omit ranges holding tonight's new
      addresses. Parse the already-downloaded TLD pages for tonight's addresses too - no extra
      download, no output build
- [x] **Validate range endpoints when parsing, not on lookup.** `_parse_gzipped_iptoasn`
      (`src/build/tlds.py:771`) accepts endpoint strings unvalidated and `ASNLookup.lookup`
      (`src/parse/iptoasn.py:161`) parses the end address only when that range is selected, so a
      malformed end address stays invisible to old probes and raises `AddressValueError` on a new
      one
- [x] **Zero or missing denominator is an error, never healthy.** `0/0` must not read as 100%
- [x] Coverage does **not** subsume a record-count floor. Two ranges spanning all of v4 and v6 give
      100% coverage from two records
- [x] `bin/check-asn-drift`, a bash wrapper over `bin/check-asn-drift.py` so it runs under uv
      the way `bin/lint` invokes `bin/lint-json.py`: health first, then
      `DRIFT <slug> <label>` and `RETURNED <slug> <label>` lines plus an `asn check: ` summary.
      Exit 0 clean, 1 drift, 2 error. Health failure short-circuits drift reporting, because bad
      input manufactures a full set of false DRIFT lines
- [x] **Failure contract, so "never blocks" is real.** Only an explicit healthy result permits
      `--all`. A failed evaluation, a missing output, or a timeout selects `--preserve-asn`. None of
      those may fail the producer job - `update-data.yaml:330` requires it to succeed
- [x] **Alert on unhealthy or indeterminate health regardless of the mode chosen.** Tying the alert
      to a *downgrade* leaves a corrupt artifact silent on every preserve night, since those nights
      have no downgrade. Repetition policy can differ
- [x] **A recovery trigger, because fallback is not self-healing.** `--all` runs only on an IANA
      source change, so an `Unknown` committed during fallback is re-copied every preserve night
      until the next source change. Force `--all` when the artifact is healthy and the committed
      graph still carries fallback damage
- [x] Fixtures: absent, corrupt gzip, valid gzip with malformed TSV, malformed range endpoint,
      partial coverage missing one address family, label collapse to a sentinel, two-giant-ranges,
      zero denominator, and **healthy controls at each threshold boundary**

### Accepted cost of a fallback night

`_asn_lookup_from_committed` (`src/build/tlds.py:707`) indexes **addresses**, not TLDs. So the
degradation is not limited to brand-new TLDs:

- Any address absent from the committed population gets `asn: 0`, `as_org: "Unknown"`,
  `as_country: "None"` - including a *replaced* address on an existing TLD.
- A new TLD reusing already-known addresses keeps full enrichment.
- A missing label removes that address's `as_org_slugs` and `as_org_aliases`
  (`src/build/tlds.py:698`) and the matching `organizations.json` operator relationship.
- Existing addresses keep whatever routing metadata was committed, which may itself be stale.
  Committed does not mean last known *good*.

The mode still rebuilds everything else and applies current `data/manual/` curation.

### Deferred, deliberately

- [x] **Freshness has no threshold.** `tests.yaml:71` takes the latest successful producer run with
      no age check and artifacts live 45 days, so a prolonged producer outage leaves a stale but
      healthy-looking artifact eligible. The gzip header mtime is one observation, not an
      established upstream convention, and `now - mtime <= limit` accepts a future timestamp. M3
      ships without an age gate and does not claim freshness. Start recording retrieval time and
      content hash so a later policy can be derived from measurement
- [x] **Label correctness is out of scope.** A permutation of operator labels across existing ASN
      records preserves coverage, cardinality, address counts and record counts alike. Detecting it
      needs an independent reference, not a self-consistency check
- [x] **Address-count drift needs an anchor, not only a ratchet.** Comparing each night to the last
      lets 1% nightly shrinkage reach 36.6% of the original population in 100 nights with every step
      passing. M3 uses a fixed floor from the table above; a rebaseable anchor is M4's concern

## M4: archival automation

The only milestone needing **write** credentials.

**Scope decided 2026-09-12: curated labels only.** M4 proposes changes to `data/manual/`, the way
`check-coordinates.yaml` does; generated ASN values keep riding the nightly patch. Three reasons.
The coordinate workflow this is modelled on PRs the curated seed, not `data/generated/`. A generated
`as_org` change carries no decision - it restates what iptoasn says, so a PR adds a merge step with
no judgment attached. And ASN fields live inside `tlds.json`, so splitting them out means two PRs
racing on one file or holding the nightly patch back.

Measured, night-to-night `as_org` churn is 0-16 addresses of ~8,950, so volume was **not** the
reason: a generated-ASN PR would have been perfectly reviewable. Accepted loss: a *wrong* `as_org`
never surfaces, but that is the label-correctness problem M3 defers, which a PR would not catch
either.

- [ ] `bin/ci-archive-asn-labels` moves drifted labels into `archived.asn`, sets `archived_on`, preserves sort order, drops an emptied `source_names.asn`, then calls `ci-make-data-patch data/manual`
- [ ] Persists through the atomic writer behind `write_json_if_changed`. `canonicalize_json_file` only re-reads and reformats a path, so it cannot save a modified object
- [ ] Never moves an entry out of `archived`, never rewrites an existing `archived_on`
- [ ] Rebuilds the resolver from the transformed seed and refuses the patch on any new collision or changed resolution
- [ ] **Pending-date semantics.** Each run rebuilds from `main`, which holds no pending entry, so a regenerated `archived_on` makes unchanged drift differ day to day. `ci-land-data-patch:259` sets `new_content` by diffing the guarded files, so the date alone would trigger a daily comment. Carry dates forward from the pending branch for labels still in the proposal, or compare membership separately for notification purposes. Test across two UTC dates; a same-day rerun misses this
- [ ] **Input guard covers `data/source/` too**, not just `data/manual`. ASN detection depends on the root database and TLD pages, so the coordinate rebase guard (`check-coordinates.yaml:170`) is insufficient
- [ ] State transitions, each with an expected outcome and a test: unchanged drift; partial return; complete return; pending `{A}` becomes `{B}`; auto-closed then recurs; human-closed then recurs; detector error while a PR is open (must not read as clearance); human-modified branch then zero drift
- [ ] **When drift clears the open PR is closed with a comment**, and repeated clean runs do not repeat it. `check-coordinates.yaml:139` skips signing with no patch, which would strand the proposal. This closure path bypasses the ownership checks in the commit path unless handled
- [ ] `bin/ci-open-drift-pr` takes title, subject, preamble **and reviewer instructions** as parameters. Line 72's Wikidata instruction would otherwise ship in every ASN PR
- [ ] **Unchanged runs are silent.** Lines 75-81 comment before consulting `new_content`. Tests assert the absence of the call, not just the outcome string
- [ ] The coordinate caller keeps its current strings; `tests/ci/test_ci_open_drift_pr.py` passes unchanged
- [ ] `.github/workflows/check-asn-drift.yaml`, two jobs, daily 01:00 UTC between the 00:00 producer and 02:00 consumer
- [ ] Copy artifact acquisition from `tests.yaml:66-85` with `actions: read`; `check-coordinates.yaml` has neither
- [ ] Add the workflow to `TestCredentialBoundary` (`tests/ci/test_ci_data_patch.py:879`), which enumerates by name
- [ ] Alert-delivery guard, signing-key `rm -f`, per-step timeouts; `actionlint` by hand

---

## M-docs: consumer contract - **DONE**

Lands with M2, since that is when the shape changes.

- [x] `README.md:300` promises "no record is ever orphaned"; archived-only orgs and orgs without `roles` break it
- [x] `README.md:306` calls `aliases` "hand-added historical"; document the split
- [x] Memory entry for the schema decision, per `AGENTS.md`
- [x] `src/build/organizations.py:58` copies every seed key into the published artifact, so `archived` is consumer-visible. Cover an archived-only org

## Verified

- **`source_names` has exactly one consumer**, `build_resolver` (`src/parse/organizations.py:74`).
- **Archiving keeps an org's role only while the label still appears in raw data.** Verified in-process that an org resolves on `asn` with its label relocated within the seed. That covers relocation, **not** disappearance from upstream, which is the drift case - hence the orphan rule above.
- **`aliases` are not source-scoped.** `fallbacks = [display_name, *aliases]` is indexed into every bucket, which is why Phase 1 narrows rather than preserves.

## Open questions

- **Typo detection for `asn` is given up.** A mistyped label never matches, so the automation archives it on the first run and it leaves the drift report. An org with other labels keeps its roles, so the orphan check does not catch it either. Distinguishing a never-seen label from one that stopped matching needs a record of prior observation, which this design deliberately does not keep.
- Whether the archive PR should auto-merge. Deferred: the `asn` warn already keeps the nightly moving.
