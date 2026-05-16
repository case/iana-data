---
title: Per-TLD JSON publication
summary: Publish data/generated/tld/<slug>.json per TLD. plus a slim tlds-index.json catalog, alongside the existing bulk tlds.json
created: 2026-05-15
author: Eric Case
tags: [log, decision, output-format, build]
---

# 2026-05-15 - Per-TLD JSON publication

`build_tlds_json` now writes three artifact shapes from one build:

- `data/generated/tlds.json` — bulk, unchanged
- `data/generated/tld/<slug>.json` — one self-contained file per TLD (~1594), each carrying `publication`, `sources`, and the full `tld` record
- `data/generated/tlds-index.json` — slim catalogue with `tld`, `tld_unicode` (IDN only), `type`, `delegated`, `tld_created`, `tld_updated`

Per-TLD filenames use the A-label (`xn--*.json`), never the U-label, so filenames are filesystem-safe and stable across IDN normalization changes.

## Why

Bulk `tlds.json` is fine for consumers that need the whole set; it's heavy for consumers that want one TLD. Per-TLD files let CDNs serve cheap direct fetches (`/tld/com.json`), and the slim index lets clients discover-then-fetch without parsing the bulk.

## Invariant

`tlds-index.json` never references a per-TLD file that failed to write. `build_tlds_json` aborts after `_write_per_tld_files` if any slug failed, before `_write_tlds_index`. Guarded by `test_build_aborts_index_when_per_tld_write_fails`.

## Cost noted

`data/generated/tld/` is committed under the same convention as `data/generated/tlds.json`. Daily update-data PRs now include per-TLD diffs in addition to the bulk diff. Open question: whether to `.gitignore` this directory and treat it as build-output-only. Not decided yet.
