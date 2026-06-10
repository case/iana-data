---
title: as_org friendly names may map a transit backbone to the true DNS operator
summary: When hostname evidence proves a single DNS operator behind a telecom-backbone ASN, that backbone's as_org string may be folded into the operator's source_names.asn, accepting that the mapping is global.
created: 2026-06-07
author: Eric Case
tags: [log, decision, manual-data, organizations, asn]
---

# 2026-06-07 - as_org transit-backbone operator mapping

`organizations.json` friendly names usually map an `as_org` string to the entity that operates that ASN, because most TLD DNS providers run dedicated DNS ASNs (Netnod, AFRINIC, RIPE NCC, Gransy). This entry records the exception: an `as_org` string that names a general-purpose transit backbone may be folded into a DNS operator's `source_names.asn` when the nameserver hostnames prove that operator runs the node.

## Trigger case: ZDNS in Chinese telecom backbones

ZDNS runs an anycast cluster `{a..j}.zdnscloud.{cn,com}` serving 22 Chinese TLDs (.baidu, .icbc, .top, .wang, and IDN gTLDs). Most nodes sit in ZDNS's own ASNs (AS38345, AS24149) and resolve correctly. Two nodes do not:

- `f.zdnscloud.cn` -> AS4837 `CHINA169-BACKBONE CHINA UNICOM China169 Backbone`
- `g.zdnscloud.com` -> AS56048 `CMNET-BEIJING-AP China Mobile Communicaitons Corporation`

Both telecom AS strings were added to the existing **ZDNS** record. In the current data each of these ASNs carries *only* the ZDNS node (AS4837 -> only `f.zdnscloud.cn`, AS56048 -> only `g.zdnscloud.com`), so the attribution is exact today.

## Why fold into the operator (not the telecom)

The dataset's purpose is identifying who operates TLD DNS. China Unicom / China Mobile are transit networks; they do not operate .baidu or .icbc DNS. Mapping the backbone to its telecom owner would assign the telecom the `asn.operator` role for TLDs it does not run. Leaving it unnamed would drop real ZDNS infrastructure. Folding into ZDNS is the only option that attributes the operator correctly.

## The fragility, accepted knowingly

The resolver matches `as_org` strings **globally** (`src/parse/organizations.py`), so ZDNS now claims every TLD nameserver IP that routes through AS4837 or AS56048. If a future data refresh adds a non-ZDNS TLD nameserver hosted in those backbones, it would be silently misattributed to ZDNS. This is acceptable because (1) it has not happened, (2) these ASNs carry nothing but ZDNS nodes today, and (3) `test_source_names_appear_in_raw_data` still holds. A per-hostname operator attribution would remove the fragility but is an architecture change, not a data edit.

## Rule of thumb for future entries

Only fold a transit-backbone `as_org` string into an operator when the hostname evidence is unambiguous (operator-owned hostname like `*.zdnscloud.*`) **and** that ASN carries only that operator's nameservers in the current data. Otherwise leave it unnamed rather than risk global misattribution. Verify with: list distinct `hostname` values whose IPs fall in the candidate ASN.

## Counter-case: hosting/IaaS ASNs to leave unnamed (OVH, AS16276)

AS16276 `OVH` (7 TLDs) was investigated and deliberately **left unnamed**. It is multi-tenant hosting, not a DNS operator:

- Its nameservers are 13 distinct third-party hostnames across 9 unrelated domains (`nic.cg`, `dns.md`, `malagasy.com`, `neoip.com`, `admin.net`, `dns.business`, `u-registry.com`, `dotukr.com`, `num.net.ua`) serving 7 different ccTLDs/gTLDs (`.cg .md .mg .sl .tg .merck .xn--j1amh`).
- PeeringDB classifies AS16276 as `info_type: "Content"` (OVHcloud, 10-20Tbps global hosting).
- Per-IP: all `OVH SAS`, `anycast: false`, scattered across independent datacenters (Montréal/Strasbourg/Hillsboro); `ns-mg.malagasy.com` reverse-resolves to `vps-974f988e.vps.ovh.net` (a literal customer VPS).

The real operators are the individual registries renting OVH compute; mapping `OVH` would falsely assign OVHcloud the `asn.operator` role. No data edit was made.

## Carrier-AS folds: size matters (GlobalConnect folded, Cogent skipped)

When an operator's own nameserver rides a carrier's AS (the ZDNS shape), the carrier's *size* decides whether to fold:

- **Folded:** `GLOBALCONNECT-` (AS2116, regional Nordic carrier) carries only `y.nic.no` -> folded into Norid.no. A niche regional AS that is sole-tenant today is low-risk.
- **Skipped:** `COGENT-174` (AS174, the world's largest tier-1 transit) carries only `be.dns.eu` today, but folding a global-transit string into an operator is too fragile - future snapshots will almost certainly add unrelated TLD nameservers in Cogent space. Left unnamed. Note `.eu` is anycast across many providers (ARNES.si, DENIC.de, Netnod, RcodeZero) already mapped to each provider; EURid has no ASN of its own here (registry-level only).
- **Skipped:** `HINET` (AS3462) + `TFN-TW` (AS9924) carry only TWNIC's `.tw`/`.台灣` nodes today, but they're large Taiwanese ISPs - same fragility as Cogent. `.tw` is multi-provider anycast across ~10 networks (Microsoft, Google, PCH, APNIC already mapped to each); TWNIC has no ASN of its own here. Don't create a TWNIC org from ISP-host strings.

Pattern across `.eu`/`.pl`/`.tw`: a registry runs DNS as multi-provider anycast; attribute each node to its *provider* when that provider is a real operator, skip pure ISP/transit hosts, and leave the registry itself at the IANA registry level (no asn.operator).

## Triage heuristic (check before researching an opaque ASN)

1. **Fan-out**: list distinct hostname domains in the ASN. One operator-owned family -> likely an operator. Many unrelated third-party domains -> hosting/transit; skip.
2. **PeeringDB `info_type`** (`https://www.peeringdb.com/api/net?asn=<n>`): `Content` / `NSP` / `Cable/DSL/ISP` ≈ hosting/transit (skip); a registry or DNS-services org won't classify as "Content".
3. **Per-IP anycast + PTR** (ipinfo IP lookups work on the free token; the ASN API does not): real DNS operators show coordinated anycast; `vps-*.vps.ovh.net`-style PTRs and `anycast:false` across scattered DCs mean IaaS.
