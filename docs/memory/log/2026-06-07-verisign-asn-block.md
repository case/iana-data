---
title: Verisign runs a per-instance ASN block (AS36616-36632), each a separate as_org string
summary: Verisign assigns one ASN per authoritative-server instance ([letter]GTLD for the gtld-servers.net letters a-m plus X/Y/Z clouds, AROOT for the roots it runs). Each surfaces as its own opaque as_org string and folds into the one VeriSign record as it appears in the data.
created: 2026-06-07
author: Eric Case
tags: [log, decision, manual-data, organizations, asn, verisign]
---

# 2026-06-07 - Verisign per-instance ASN block

Verisign operates a contiguous ASN block where each ASN names a single authoritative-server instance, not a distinct organization. Per bgplookingglass.com's AS-number list, AS36616-36632 are all registered to "VeriSign Global Registry Services" with opaque labels:

- `[letter]GTLD` - the per-letter gTLD nameserver anycast clouds (`a.gtld-servers.net` .. `m.gtld-servers.net`, which serve .com/.net and, via `*.edu-servers.net`, .edu). e.g. AGTLD, CGTLD, HGTLD (AS36623), MGTLD, plus extra XGTLD/YGTLD/ZGTLD clouds.
- `AROOT` (AS36627) - a root server. Verisign operates `a.root-servers.net` and `j.root-servers.net` (2 of the 13 roots), so the root labels cover only the roots Verisign runs, not all 13.

## Confirmation method

For AS36623: ARIN RDAP `https://rdap.arin.net/registry/autnum/36623` returns `name: HGTLD`, registrant entity handle `VGRS` / "VeriSign Global Registry Services". Corroborated by the nameserver hostnames whose IPs route through it in our data (`j/k/l/m.gtld-servers.net`, `*.edu-servers.net`, `ac3.nstld.com` - all Verisign infra). The ASN *label* does not map 1:1 to the hostname *letter*: AS36623 is labeled HGTLD but answers for j/k/l/m, because these are anycast clouds announcing prefixes spanning multiple letters. Treat the label as Verisign's internal name, not a hostname map.

## What we added

Only `HGTLD` (AS36623) is present in the data, so only `HGTLD` was added to the VeriSign record's `source_names.asn` (joining VERISIGN-AS, VRSN-AC28, VRSN-AC50-340; VGRS-AC25 also resolves via the `aliases` cross-bucket fallback in `src/parse/organizations.py`). This raised friendly-name coverage 83.0% -> 83.5%. In the current iptoasn snapshot all 18 of HGTLD's TLDs (`.com`, `.net`, `.edu`, `.name`, `.cc`, the `.verisign` brand TLD, and 11 IDN gTLDs) sit under AS36623/`HGTLD`.

## Why not pre-load the sibling labels

`test_source_names_appear_in_raw_data` requires every `source_names.asn` string to match a raw value in the built `tlds.json` character-for-character. The sibling labels (AGTLD, GGTLD, KGTLD, AROOT, ...) carry no TLD nameserver in our data, so adding them speculatively fails the test. If a future snapshot routes a TLD nameserver IP into another ASN in this block, it will surface as the next unnamed string under its own `[letter]GTLD`/`AROOT` label - recognize it as Verisign and fold it in then. (iptoasn IP->ASN assignments are not perfectly stable over time, so which sibling a given Verisign IP carries can shift between snapshots; always map against a current iptoasn.) See [2026-06-07 as_org transit-backbone operator mapping](2026-06-07-asn-transit-operator.md) for the related one-org-many-strings pattern.
