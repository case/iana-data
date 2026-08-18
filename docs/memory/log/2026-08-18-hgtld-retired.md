---
title: Verisign's HGTLD label left iptoasn entirely; retire it to aliases
summary: AS36623/HGTLD disappeared from the iptoasn table between the 2026-07-15 and 2026-08-11 snapshots. Its prefixes now announce under AS397198/397200/397204 labeled VRSN-AC28, already seeded. Fix is data - retire HGTLD to aliases. Broke the nightly update-data run for 7 consecutive days.
created: 2026-08-18
author: Eric Case
tags: [log, decision, manual-data, organizations, asn, drift, verisign]
---

# 2026-08-18 - HGTLD retired

`test_source_names_appear_in_raw_data` failed with `verisign / asn / 'HGTLD' - no raw match` and no near matches. Same class of upstream drift as [2026-07-16 teleinfo-asn-rename](2026-07-16-teleinfo-asn-rename.md), one step further: the string did not get renamed, the whole ASN left the table.

| | ASN | `as_org` string |
|---|---|---|
| Before (2026-07-15 snapshot) | 36623 | `HGTLD` |
| Live (2026-08-18 CI artifact) | 397200 | `VRSN-AC28` |

`192.41.162.0/24`, `192.48.79.0/24`, `192.52.178.0/24`, `192.55.83.0/24` and their v6 siblings all moved. AS36623 no longer appears at any row, and `grep -c HGTLD` over the current table returns 0 - the entire `[letter]GTLD` label family is gone, with no `*GTLD`-suffixed `as_org` left anywhere. Verisign's surviving labels are VGRS-REGISTRY-AS, VERISIGN-CORP, VERISIGNGRS, VERISIGN-INC, VERISIGN-AS, VGRS-AC22, VERISIGN-ILG1, VRSN-AC50-340 and VRSN-AC28.

## Fix

`HGTLD` moved from `verisign.source_names.asn` to `aliases` in `data/manual/organizations.json`. No reseed needed: the receiving label `VRSN-AC28` was already in `source_names.asn`, so TLD attribution is unchanged. `aliases` resolve in every bucket via the cross-bucket fallback in `src/parse/organizations.py`, so the mapping survives if the label ever returns.

This closes the "fold them in as they appear, retire them as they leave" cycle opened by [2026-06-07 verisign-asn-block](2026-06-07-verisign-asn-block.md); that entry's "What we added" section is now historical.

## Detection lag

The nightly `Update IANA Data` run failed every day from 2026-08-11 to 2026-08-18 on this one assertion, and the test step gates the commit step - so no source-data refresh landed for a week. The pushover notification step fired each time but ran with an invalid token (`application token must be supplied`), so nothing was delivered. Worth fixing the token or adding a second channel; a data repo whose only signal is a silent nightly failure goes stale invisibly.
