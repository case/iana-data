---
title: iptoasn reworded its labels, so curated asn names were re-spelled by ASN number
summary: iptoasn changed its label text between August and November 2026, which drifted 72 of 74 curated asn labels. The old spellings moved to archived.asn and the new ones were added to source_names.asn, matched by ASN number.
created: 2026-11-11
author: Eric Case
tags: [log, decision, asn, iptoasn, organizations]
---

# 2026-11-11 - iptoasn label respelling

iptoasn now appends the holder name to most labels, and prefixes some with the ASN:

| ASN   | Before       | After                         |
| ----- | ------------ | ----------------------------- |
| 42    | `WOODYNET-1` | `WOODYNET-1 - WoodyNet, Inc.` |
| 27678 | `NIC Chile`  | `AS27678 - NIC Chile`         |

The drift check reported 72 of the 74 curated `asn` labels. The drift PR would have archived them
and left 29 orgs with no current match. Every label is still the same network under a new name.

## Fix

- The 72 drifted labels moved to `archived.asn`, as the drift automation would have done.
- For each archived label, the new spelling was found by ASN number: the label's ASNs in the
  previous artifact, then those ASNs' labels in the current one.
- A new spelling was added to `source_names.asn` only when it appears on a TLD nameserver address
  in a full build. That drops ASNs a label shares with an unrelated network, such as
  `COMPASS-AS Compass Education Holdings Limited` beside `ryce`'s `COMPASS-AS Compass-Verlag GmbH`.
- None of the 82 added labels is claimed by another org.

`HGTLD`, `VERISIGN-AS`, `VGRS-AC25`, `CLOUDFLARENET` and `CAICTNET` have no current nameserver
address, so they stay archived with no successor.

## Consequence

Until the nightly runs `bin/build --all`, the committed `tlds.json` carries the old labels. The new
names show as tolerated `AsnDriftWarning`s in `bin/test` until then.
