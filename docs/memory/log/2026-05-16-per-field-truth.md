---
title: Per-field source-of-truth for IANA data
summary: Each IANA source is authoritative for a specific field set; the build does not cross-validate redundant sources. Encoded by reconciliation tests in tests/integration/test_build_reconciliation.py.
created: 2026-05-16
author: Eric Case
tags: [log, decision, architecture, build, testing]
---

# 2026-05-16 - Per-field source-of-truth

Each IANA data source is authoritative for a specific set of fields. The build never asks "do these two sources agree" for redundant data; it asks "does each source agree with the field it owns."

## Authoritative source per field

| Source                                  | Authoritative for                                          | Role                |
|-----------------------------------------|------------------------------------------------------------|---------------------|
| `iana-root.html` (Root Zone DB)         | TLD set membership, delegation status, manager, iana_tag   | Primary build input |
| `iana-rdap.json` (RDAP bootstrap)       | RDAP server URLs for TLDs IANA has bootstrapped (predominantly gTLDs) | Annotation input    |
| `supplemental-cctld-rdap.json` (manual) | ccTLD RDAP servers not registered in IANA's bootstrap     | Annotation input    |
| `icann-registry-agreement-table.csv`    | gTLD agreement metadata (sponsorship, brand status)        | Annotation input    |
| `iana-tlds.txt` (alphabetical list)     | Nothing the build consumes                                 | Advisory only       |

## Why

Source-of-truth-by-field rather than source-of-truth-for-everything. The same logical fact (e.g., "is `.merck` delegated") appears in multiple IANA sources on different publication cadences. Asserting cross-source agreement as a build invariant fails whenever IANA legitimately publishes inconsistent intermediate state.

The .merck drift incident (commit 9a2c1b9, March 2026) is the precedent: root DB and tlds.txt disagreed on `.merck`'s delegation. The fix demoted tlds.txt from "build input" to "advisory monitoring signal" and rewrote the build to derive delegation from root DB alone.

## Encoded by

- `tests/integration/test_build_reconciliation.py` — five tests asserting per-field invariants:
  - Set equality between built tlds.json and root DB
  - Every IANA RDAP bootstrap TLD present in tlds.json with `rdap_server` populated and `annotations.rdap_source == "IANA"`
  - Per-TLD delegation flag agreement vs root DB
  - TLD count within 5% drift baseline (catches systematic parser regression that cross-source equality misses)
  - AST-based architectural guard: build never imports any symbol from `src/parse/tlds_txt`
- `tests/integration/test_source_drift.py` — warns on root-DB-vs-tlds.txt drift, does not fail. The warning-only treatment is load-bearing: flipping it to failure would resurrect the .merck-class bug.
- `tests/integration/test_data_integrity.py` — count-based variants kept alongside the new set-equality tests as descriptive companions; their failure messages name the specific count mismatch (delegated, undelegated, total math).

## Residual gap

The cross-source reconciliation tests compare each parser's output against a tlds.json built from that same parser (root DB for tests 1, 3; RDAP bootstrap for test 2). A parser regression that silently shrinks the source-side set would not be caught — both sides shrink together. `test_built_tld_count_within_baseline_threshold` partially closes this for the root DB parser with an independent inline baseline (1594 total, 1437 delegated as of 2026-05-16, 5% threshold). A full regression-against-prior-committed-tlds.json check that diffs the actual set, not just counts, is future work and would cover all parsers symmetrically.
