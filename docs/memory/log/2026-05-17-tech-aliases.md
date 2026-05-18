---
title: orgs.tech aliasing via tech-aliases.json
summary: Mirror tld-manager-aliases.json plumbing for orgs.tech, producing annotations.tech_alias so downstream consumers can dedupe noisy registry-operator strings.
created: 2026-05-17
author: Eric Case
tags: [log, decision, manual-data, annotations]
---

# 2026-05-17 - orgs.tech aliasing

A second manual-alias file, `data/manual/tech-aliases.json`, canonicalizes orgs.tech strings the same way `tld-manager-aliases.json` canonicalizes the root-DB manager field. The build emits the result as `annotations.tech_alias`.

## Why

A downstream consumer (how-domains-work) reverse-indexes TLDs by tech operator for an Ecosystem → Technical Operators page. Without dedup, "Identity Digital Limited" (309 TLDs) and "Identity Digital Inc." (83 TLDs) fragment what should be one entity at ~455 TLDs. The manager-alias plumbing solves the same problem for managers; this is the parallel mechanism for tech operators.

## Shape

File shape mirrors `tld-manager-aliases.json` exactly: top-level `techAliases` (vs `managerAliases`), then canonical-name → array of `{name, source}` entries. Parser returns the reverse lookup (raw → canonical) for O(1) match during build.

## Wiring

- `src/parse/tech_aliases.py` — parallel to `src/parse/tld_manager_aliases.py`
- `src/config.py` — `MANUAL_FILES["TECH_ALIASES"] = "tech-aliases.json"`
- `src/build/tlds.py` — loads aliases alongside `tld_manager_aliases`; matches against `orgs.tech` (not `orgs.tld_manager`); sets `annotations.tech_alias` when matched
- `data/manual/tech-aliases.json` — initial high-confidence dedups (Identity Digital, Google, NIXI, AFNIC)

## Editorial decisions baked into initial content

- **Afilias / Afilias Limited / Donuts Inc / Internet Computer Bureau Ltd[Limited] → Identity Digital**: factually correct via the lineage Afilias → Donuts (2020) → Identity Digital (2022), and ICB → Afilias (acquired 2005); folded with `source:` URLs so the merge is auditable.
- **GoDaddy Registry, CentralNic, GRS Domains**: not merged. These overlap historically (GRS lineage absorbed by CentralNic) but a tech-operator dedup needs human verification; default to separate entries.
- **Aliasing orgs.admin**: deferred. Out of scope unless the downstream site surfaces Admins as an entity type.

## Renaming caveat

`tld_manager_alias` is not renamed for naming consistency with `tech_alias` — it's load-bearing for existing consumers. The asymmetric annotation-field naming (`tld_manager_alias` for managers, `tech_alias` for tech) is intentional.

## Canonical-name alignment between the two files

The two alias files share a canonical-name namespace: any canonical that appears in both `tld-manager-aliases.json` and `tech-aliases.json` uses the same spelling (e.g. "Google Registry", "Tucows Registry", "Identity Digital", "VeriSign"). Canonicals that exist only in one file are fine (CentralNic, CIRA, Nominet, etc. on the tech side). Enforced by `tests/integration/test_alias_consistency.py`, which fails if any raw name appears in both files with different canonicals — the test catches accidental drift introduced by future hand-edits.
