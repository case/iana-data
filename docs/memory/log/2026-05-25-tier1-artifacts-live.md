---
title: Tier 1 artifacts live: organizations, places, cultures, agreements
summary: All four typed-graph artifacts now built, consumed, and integrity-tested; supersedes the SEED-ONLY note from 2026-05-24
created: 2026-05-25
author: Eric Case
tags: [schema, typed-graph, organizations, places, cultures, agreements]
---

# Tier 1 artifacts live (2026-05-25)

All four typed-graph artifacts are now built and consumed by the pipeline.

- **`data/generated/organizations.json`**: was seeded but unused on 2026-05-24; now built by `src/build/organizations.py`, sorted by `slug`, with reverse-indexed `roles.{iana,icann,asn}`. The three legacy alias files (`tech-aliases.json`, `tld-manager-aliases.json`, `as-org-aliases.json`) are gone; `annotations.iana_*_alias` / `iana_*_slug` / `icann_registry_operator_*` / `as_org_*` all resolve via this single file.
- **`data/generated/places.json`**: built by `src/build/places.py`. Countries derived mechanically (pycountry + `CCTLD_OVERRIDES`); subdivisions, cities, and supranational records hand-curated in `data/manual/places.json`; dependent territories from `data/manual/dependent-territories.json`. Single `country` subtype + `iso_designation` field captures dependent / reserved / special-area status.
- **`data/generated/cultures.json`**: built by `src/build/cultures.py`. 12 records; transposes `annotations.cultural_affiliation` → `tlds[]`.
- **`data/generated/agreements.json`**: built by `src/build/agreements.py`. 5 records (`base`, `brand`, `community`, `sponsored`, `non_sponsored`); slugs from `REGISTRY_AGREEMENT_TYPE_MAPPING`; `source_names.icann` preserves the verbatim CSV string.
- **New annotation primitives** added to `data/manual/annotations.json`: `bayern`, `corsica`, `okinawa`, `ruhr`, `ryukyu` (subdivisions); `ist` (city); `xn--ngbrx` (`cultural_affiliation: arab`).
- **JSON linting:** `bin/lint-json.py` validates every committed JSON file (syntax + canonical formatting). Wired into `bin/lint`.
- **Integrity tests** (`tests/integration/test_*_integrity.py`) enforce cross-file FKs as hard failures, per the "integrity-as-tests" project rule.

Per-artifact schemas documented in the Obsidian vault at [[2026-05-20 - orgs.json schema]], [[2026-05-27 - places.json schema]], [[2026-05-27 - cultures.json schema]], [[2026-05-27 - agreements.json schema]].
