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
