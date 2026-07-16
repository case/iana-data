---
title: iptoasn AS drift stranded teleinfo and verisign asn seeds; reseed to live strings, retire departed ones to aliases
summary: One iptoasn refresh window renamed CAICT's AS (teleinfo, AS139137 "CAICTNET..." -> AS138457 "CAICT-AS-AP...") and migrated Verisign's .com/.net nameservers off "VERISIGN-AS" onto VRSN-AC28/VRSN-AC50-340, so both orgs' source_names.asn seeds matched no live raw value. Fix is data: reseed to the live string(s), retire the departed one to aliases. Reproduce against CI's pinned update-iptoasn artifact, not iptoasn.com live-latest.
created: 2026-07-16
author: Eric Case
tags: [log, decision, manual-data, organizations, asn, drift]
---

# 2026-07-16 - teleinfo AS rename

CI integrity tests failed with `teleinfo` mapping to zero TLDs (`test_every_org_has_at_least_one_role`) and its `source_names.asn` seed matching no raw value (`test_source_names_appear_in_raw_data`). Root cause was upstream drift, not a code bug: the org is resolved purely by an ASN operator name, and `iptoasn` renamed CAICT's AS.

| | ASN | `as_org` string |
|---|---|---|
| Before (committed snapshot) | 139137 | `CAICTNET Chinese Academy of Telecommunication Research` |
| Live (2026-07-16) | 138457 | `CAICT-AS-AP China Academy of Information and Communications Technology` |

All 10 teleinfo TLDs' nameservers sit in `103.61.60.0/24`, which flipped ASN and name in one refresh. Same real-world operator (CAICT, formerly the Chinese Academy of Telecommunication Research); the seed string just went stale.

## Fix

In `data/manual/organizations.json`, reseed `teleinfo.source_names.asn` to the new string and move the old name into `aliases` (retired names live in `aliases`, matching `verisign -> VGRS-AC25`, `cloudflare -> CLOUDFLARENET`). `display_name` stays "Teleinfo" - the seed is a network-operator join key, not a display label.

## Co-occurring drift: verisign (fixed in the same pass)

The same refresh window also stranded verisign's `VERISIGN-AS` asn seed. Its `.com`/`.net` nameservers (e.g. `ac4.nstld.com` 192.42.176.30) migrated off AS25485/AS29403 (`VERISIGN-AS`) onto `VRSN-AC28` and a newly appearing `VRSN-AC50-340`. `VERISIGN-AS` is still a real string in the `iptoasn` table but no longer appears on any TLD nameserver, so `test_source_names_appear_in_raw_data` flags it. Fix: `VRSN-AC50-340` was already seeded; retire `VERISIGN-AS` to `aliases` (joins `VGRS-AC25`). Consistent with [2026-06-07 verisign-asn-block](2026-06-07-verisign-asn-block.md): fold per-instance Verisign AS strings in as they appear, retire them as they leave.

## Reproducing CI deterministically (not "download latest")

`iptoasn.com`'s live file changes through the day, so downloading the bleeding-edge file makes local run *ahead* of CI and surface drift CI's pinned snapshot hasn't seen. CI does not use live-latest: `update-data.yaml` pulls the artifact from the newest **successful** `update-iptoasn` run. To match CI exactly:

```
RUN=$(gh run list --workflow=update-iptoasn.yaml --status=success --limit=1 --json databaseId -q '.[0].databaseId' --repo case/iana-data)
gh run download "$RUN" --repo case/iana-data --pattern 'iptoasn-*' --dir data/source/iptoasn
```

The integration test builds with `preserve_asn=False`, so it reads this file directly - no `bin/build` needed to reproduce. (`data/source/iptoasn/*.gz` is git-ignored; `data/generated/` still carries older names and does not gate this test.)

## Pattern

An `as_org` seed (especially an `as_org`-only org with no iana/icann seed) is a single point of failure against upstream AS renames/re-routing: one string change strands every TLD it covered. When an integrity failure names such an org, reproduce against CI's pinned artifact (above), then diff which `as_org` strings actually appear on that operator's nameservers now - confirm rename/migration vs genuine deletion before editing. Fix is always data: reseed to the live string(s), retire the departed one to `aliases`. Related: [2026-06-07 asn-transit-operator](2026-06-07-asn-transit-operator.md).
