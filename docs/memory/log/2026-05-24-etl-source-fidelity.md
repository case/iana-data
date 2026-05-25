---
title: ETL source-fidelity policy (TLD pages)
summary: Extract stores a verbatim <main> slice; Transform decodes entities and selects fields
created: 2026-05-24
author: Eric Case
tags: [etl, parsing, tld-html, policy]
---

# ETL source-fidelity policy

**Policy:** Extract stores upstream verbatim; Transform selects fields and corrects issues.

`download_tld_pages` previously saved `extract_main_content(response.text)`, where the old `extract_main_content` (an `HTMLParser`) **re-serialized** the page: it decoded `&amp;`->`&`, dropped HTML comments, and rewrote tags. That made the stored "source" a lossy transform, unlike every other source (`iana-root.html`, RDAP, ICANN CSV/JSON), which is stored raw and corrected in its parser.

**Change:**
- `extract_main_content` is now a **verbatim `<main>...</main>` byte-slice** (regex `<main\b[^>]*>.*?</main\s*>`, DOTALL|IGNORECASE). Entities, comments, and formatting are preserved; site chrome (≈72% of each page) is stripped; footprint ≈ unchanged (~2.5 KB/page). Returns `""` when no `<main>`, so `download_tld_pages` keeps its full-page `-full` fallback.
- `parse_tld_page` (Transform) owns decoding: the org extractors and the regex-extracted URL/server fields (`registry_url`, `whois_server`, `rdap_server`) now `html.unescape()` their captures.
- The org extractor regex now tolerates **1+ `<br>`** (`(?:\s*<br\s*/?>)+`). The old pattern required `<br><br>`, which only existed because the old `extract_main_content` turned upstream `<br/>` into `<br></br>`; on a faithful slice (raw `<br/>`) selectolax yields a single `<br>`, so the old regex silently dropped `admin`/`tech`.

**Why it mattered:** `orgs.admin` / `orgs.tech` were shipping `&amp;` into `tlds.json` (e.g. `SWITCH The Swiss Education &amp; Research Network`). `tld_manager` was unaffected only because the build overwrites it from the root-DB parser (`html.parser` decodes correctly).

**Contact data:** the `<main>` slice retains contact email/phone/fax/address (public data, kept faithfully in source). Derived data only ever extracts the org line, so PII never enters `tlds.json` (status quo, no active scrubbing).

**Guard:** `tests/build/test_tlds.py::test_build_tlds_json_no_html_entities_in_any_field` asserts `html.unescape(v) == v` for every string in every generated TLD entry (a bare `&` like `AT&T` passes; `&amp;` fails).

**Reviewed:** `/consensus` with `gemini -p` (assessment + implementation). Gemini caught the `registry_url` latent leak (folded in) and the `.text()`-concatenation pitfall in an earlier DOM-traversal draft (rejected in favor of the hardened regex).

**Download coverage:** `download_tld_pages` and the CLI now source the TLD list from `parse_root_db_tlds()` (the full root DB, ~1594) instead of `parse_tlds-alpha-by-domain.txt` (~1437 delegated). The build iterates the root DB, so the old delegated-only list left ~157 retired-but-listed TLDs (e.g. `abarth`, `an`) never refreshed. Most are revoked records with empty contact sections, so their faithful slice equals the old output; the change just keeps coverage aligned so nothing drifts.

**Phase 2 (done 2026-05-24):** re-downloaded all TLD pages to faithful slices and ran `make build`. Verified: `data/generated/tlds.json` has zero HTML entities across all fields; org names carry literal `&`. Existing `html-partial` fixtures left as-is (old re-serialized format) alongside the new faithful `ch`/`xbox` ones, giving dual-format parser coverage; re-snapshotting them was rejected to avoid coupling value assertions to drifting upstream data.
