# iana-data memory

Project decisions, architecture, and conventions. Two core files plus a dated `log/` subdir.

Agents: consult before suggesting layout, naming, dependencies, vendors, or conventions. Verify against the codebase before relying on a specific path or name - memory can lag reality.

## Core
- [Product](product.md) - what iana-data is and why; implementation-independent
- [Architecture](architecture.md) - current implementation: stack, layout, conventions

## Log (newest first)
- [2026-06-07 Verisign per-instance ASN block](log/2026-06-07-verisign-asn-block.md) - AS36616-36632 are all Verisign, one ASN per authoritative-server instance ([letter]GTLD for gtld-servers.net letters a-m plus X/Y/Z, AROOT for the roots it runs); each is a separate opaque as_org string, folded into the one VeriSign record as it appears (HGTLD/AS36623 added; other siblings not yet in data)
- [2026-06-07 as_org transit-backbone operator mapping](log/2026-06-07-asn-transit-operator.md) - fold a telecom-backbone as_org string into a DNS operator's source_names.asn only when hostname evidence is unambiguous and that ASN carries only that operator (ZDNS in China Unicom AS4837 / China Mobile AS56048); mapping is global, so misattribution is the risk
- [2026-05-30 bin/build requires explicit mode](log/2026-05-30-build-modes.md) - bare bin/build prints help; --preserve-asn (local, keep committed ASN) vs --all (full ASN refresh, CI); stops silent ASN churn from a stale iptoasn snapshot
- [2026-05-30 Country coordinate overlay](log/2026-05-30-country-coordinates.md) - data/manual/country-coordinates.json overlays info_link + P625 coordinates onto no-polygon derived countries (bv cc cx tk gi gf gp mq re yt sj ac); augment not move, identity stays derived
- [2026-05-27 Brand-status pinned](log/2026-05-27-brand-status-pinned.md) - specification_13 is application-era, CSV is current; 8 known mismatches pinned by test; README "Interpreting the data" added
- [2026-05-27 IDN language](log/2026-05-27-idn-language.md) - language_code + language_name_en for all 151 IDNs via CLDR likelySubtags + per-(script, region) and per-TLD overrides; Han-CJK Simplified/Traditional/Taiwan distinctions
- [2026-05-25 Tier 1 artifacts live](log/2026-05-25-tier1-artifacts-live.md) - all four typed-graph artifacts built and consumed; legacy alias files deleted; new annotation primitives added; supersedes 2026-05-24 SEED ONLY note
- [2026-05-25 Writer byte-equality](log/2026-05-25-writer-byte-equality.md) - write_json_if_changed compares serialized JSON (not dict equality), so field-order changes propagate to disk
- [2026-05-24 Typed-graph ingest](log/2026-05-24-typed-graph-ingest.md) - orgs.icann.* + per-TLD annotations + infrastructure type; organizations.json seeded (now superseded by 2026-05-25 Tier 1 live)
- [2026-05-24 ETL source-fidelity](log/2026-05-24-etl-source-fidelity.md) - Extract stores verbatim <main> slice; Transform decodes entities + selects fields (fixes &amp; in orgs)
- [2026-05-17 orgs.tech aliasing](log/2026-05-17-tech-aliases.md) - tech-aliases.json + annotations.tech_alias, parallel to tld_manager_alias
- [2026-05-16 Per-field source-of-truth](log/2026-05-16-per-field-truth.md) - each IANA source authoritative for a specific field set; reconciliation tests encode the rule
- [2026-05-15 Per-TLD JSON publication](log/2026-05-15-per-tld-publish.md) - per-TLD files + slim index alongside bulk tlds.json
- [2026-05-15 Atomic JSON writes](log/2026-05-15-atomic-writes.md) - NamedTemporaryFile + fsync + chmod 0o644 + os.replace pattern
- [2026-05-15 bin/ scripts replace make targets](log/2026-05-15-bin-scripts.md) - bin/setup, bin/lint, bin/test; make retains domain targets
- [2026-05-15 Switch from npm to pnpm](log/2026-05-15-pnpm.md) - pnpm-lock.yaml replaces package-lock.json
- [2026-05-15 Bootstrap memory system](log/2026-05-15-bootstrap.md) - initial setup of this memory system
