---
title: Typed-graph ingest — gTLDs, annotations, orgs seed
summary: First typed-graph slice on tlds.json — orgs.icann.*, per-TLD annotations, infrastructure type, organizations.json seed
created: 2026-05-24
author: Eric Case
tags: [schema, typed-graph, orgs, annotations, gtlds]
---

# Typed-graph ingest (Phases 0-1, shipped 2026-05-24)

> [!note] Superseded 2026-05-25
> The `organizations.json` layer described below as "SEED ONLY" was the Phase 1 state. Phase 2 shipped on 2026-05-25: the file is now built and consumed by the pipeline, and the three legacy alias files were deleted. See [2026-05-25 Tier 1 artifacts live](2026-05-25-tier1-artifacts-live.md) for the current state.

First slice of the typed-graph update and refactor.

- **`orgs.icann.*`** from the ICANN gTLDs report. New source `data/source/icann-gtlds.json` + parser `src/parse/gtlds_json.py`, keyed by gTLD. Downloaded by a standalone `scripts/gtlds/download_gtlds.py` (ICANN sources are not in the `--download` CLI flow), wired into nightly `update-data.yaml`. Excludes `registryClassDomainNameList` (100% null); stores no RSP or `uLabel` field (no per-TLD source).
- **`orgs` is now nested by source** — `orgs.iana` {sponsor, admin, tech} and `orgs.icann` {registry_operator, specification_13, contract dates} — kept alongside the legacy flat `orgs.{tld_manager, admin, tech}` (additive, nothing removed).
- **Per-TLD annotations** `geographic_scope` + `cultural_affiliation` come from one hand-curated `data/manual/annotations.json` keyed by TLD (alphabetical) — a single file, not per-concern files. ccTLD → `country` scope is derived in code; `.eu` → `supranational` is overridden in the file.
- **Type fix:** IANA `infrastructure` tag now maps to `type: "infrastructure"` (`.arpa`), was `gtld`.
- **`organizations.json` registry-identity layer — SEED ONLY.** 53 consolidated registry orgs: `display_name` (editorial), `source_names` {iana, icann, asn} (verbatim per source), `aliases`, `homepage`. **Not yet consumed by the build** — it is a seed for the future Phase 2 transpose (generate `data/generated/organizations.json`, repoint `tlds.json` annotations, then delete the three `*-aliases.json` files). `source_names` act as a literal string-match reverse-index, so they must equal the decoded `tlds.json` values (e.g. `kisa` was decoded `&amp;` → `&` to match the [[2026-05-24-etl-source-fidelity]] fix). File sorted by slug; homepages prefer the corporate-owner site. *(Update 2026-05-25: superseded by [2026-05-25 Tier 1 artifacts live](2026-05-25-tier1-artifacts-live.md). Phase 2 shipped: organizations.json is now built and consumed; the three legacy alias files were deleted.)*
