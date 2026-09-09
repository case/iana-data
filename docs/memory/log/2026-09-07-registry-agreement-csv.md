---
title: ICANN's /csvdownload is abandoned; render the table from the page's ng-state instead
summary: The registry-agreement CSV endpoint 502s on a fixed ~15.1s origin timeout and ICANN's own site never calls it - the Angular app builds the CSV in-browser from the server-rendered ng-state JSON. The downloader now fetches the page and reproduces that CSV byte for byte.
created: 2026-09-07
author: Eric Case
tags: [log, decision, source-data, icann, registry-agreements, drift, download]
---

# 2026-09-07 - Registry agreement CSV rendered from page state

`https://www.icann.org/en/registry-agreements/csvdownload` returns 502 on every request at a near-constant 15.05-15.21s, with `server-timing: cfOrigin;dur=15125`. That is an origin gateway timeout on the dynamic export, not a bot block: user agent, `Referer`, browser fingerprint headers, a carried `__cf_bm` cookie and a second network all reproduce it identically.

It has failed every scheduled `update-data` run since at least 2026-07-30, silently, because the step is `continue-on-error: true` and the committed CSV simply froze at its 2026-05-20 content.

The browser appears to work because it never fetches that URL. The `<iti-ra-csv-download>` component intercepts the click and builds the file client-side from the `ng-state` JSON already server-rendered into the page, delivered as a `blob:` URL. `/csvdownload` is vestigial, which is why it can rot for months unnoticed.

## Fix

`ICANN_URLS["REGISTRY_AGREEMENT_TABLE"]` points at `https://www.icann.org/en/registry-agreements` (200 in ~0.35s, plain httpx). `src/parse/registry_agreement_page.py` extracts `script#ng-state` -> `registry-agreements-{}.data.registryAgreementOperations.registryAgreements` and renders the CSV byte-identically to the browser's export:

- sort rows by TLD; blank `U-Label` when `uLabel` equals the TLD
- reorder `agreementType` tokens to `Base, Brand (Spec 13), Community (Spec 12), Sponsored, Non-Sponsored`, joined with `", "`; lowercase `agreementStatus`
- `agreementDate` ISO -> `%-d %b %Y` via a month table, not `strftime` (locale-independent)
- `Link` path segment is `terminated` for terminated agreements, `details` otherwise
- UTF-8 BOM, LF endings, no trailing newline, empty fields unquoted, embedded `"` doubled

Two upstream bugs disappear as a side effect: the table gains `web` (1276 rows vs 1275), and `Link` carries a real `https://www.icann.org/...` URL instead of the leaked internal `http://iti-web-icann-lax-prod/...` hostname.

An unknown `agreementType` now raises rather than sorting to the end, like every other deviation in the module - byte fidelity is its whole purpose. `AGREEMENT_TYPE_ORDER` derives from `REGISTRY_AGREEMENT_TYPE_MAPPING` in `src/config.py` so the two cannot be edited one-sidedly.

## Downloader change

`download_file()` gained an optional `transform: Callable[[str], bytes]` converting the fetched document into the bytes written. Three properties:

- **Fails closed.** A raising transform propagates to `"error"`, so a site redesign trips the pushover alert instead of committing an empty table. `extract_registry_agreements` raises `RegistryAgreementPageError` on a missing `ng-state` node, bad JSON, a missing key path, a non-list or an empty list.
- **Suppresses churn.** Rendered bytes matching the file on disk yield `"not_modified"`, needed because the page's ETag moves whenever any unrelated part of the page does. Validators are still recorded, so the next run can still get a 304.
- **Decodes as UTF-8, not `response.text`.** An `iso-8859-1` `Content-Type` would turn `Kanton Zurich` into mojibake and commit it with no error.

The `is_cache_fresh` short-circuit is skipped whenever a transform is set: it returns before the request, so the transform never runs, and a long origin `max-age` would reproduce the silent freeze exactly.

## Cache validators are keyed to a URL

Repointing the URL left `metadata.json` holding validators captured from `/csvdownload`, and conditional headers were built from the metadata key alone. `cache_data` now records the `url` it came from, and validators recorded against a different URL - or against none, which is every pre-existing entry - are discarded. One-time cost is a full 200 per source on the first run.

Validators are recorded only where the response was processed to the end: after a `content_validator` reports "unchanged", and after a transform succeeds. Never after a transform raises, or the next run answers 304 and masks the failure permanently. Recording after the `content_validator` early return matters because the three core IANA sources take that path almost nightly; skipping it made them refetch in full forever.

`last_downloaded` is the exception: it anchors the `is_cache_fresh` window and moves only when content reached disk, so a source that reports "unchanged" nightly cannot slide its own freshness window forward.

## Watch for

The `ng-state` key path is the fragile part - ICANN controls that markup and can restyle it without notice. It fails loudly by design. If `/csvdownload` is ever repaired, reverting means changing the URL **and** dropping the `transform=` argument in `scripts/registry-agreement-table/download_registry_agreement_table.py`; the URL alone feeds CSV to the HTML extractor.

## Carried in the same change

`update-data.yaml`'s source-change check now runs `git add --intent-to-add -- data/source/` and diffs against `HEAD`. Before, a new source file was untracked and a deleted one invisible, so either left `source_changed=false` and took the `--preserve-asn` path. This revises [2026-06-07 nightly manual regen](2026-06-07-nightly-manual-regen.md): a new or removed source file now triggers a full `--all` rebuild.
