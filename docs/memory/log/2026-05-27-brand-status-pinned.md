---
title: Brand-TLD status: pinning the IANA-vs-ICANN divergence
summary: specification_13 is application-era; CSV is current; 8 mismatches pinned by test; README documents the semantic split
created: 2026-05-27
author: Eric Case
tags: [schema, agreements, brand-tlds, integrity-tests, icann]
---

# Brand-TLD status divergence (2026-05-27)

The two ICANN sources answer different questions about "is this a Brand TLD":

- **`orgs.icann.specification_13`** (from `data/source/icann-gtlds.json`): application-era flag. Set at delegation, persists for life.
- **`annotations.registry_agreement_types` containing `"brand"`** (from the ICANN registry-agreement CSV): current contract. Updates on reclassification.

362 delegated gTLDs agree they're Brand. **8 disagree**, and the divergence is real signal, not noise:

| Sub-pattern | TLDs | What happened |
| ----------- | ---- | ------------- |
| Brand → aftermarket operator | `.case`, `.diy`, `.food`, `.monster`, `.sbs` | Brand owner divested; aftermarket op (Digity, INC, XYZ.COM, ShortDot) reopened to general regs |
| Brand owner opened to general | `.gmo`, `.nexus` | Original brand owner (GMO Internet, Google) opted into general registration |
| ICANN gtlds.json stale | `.baidu` | Still a closed Brand TLD operated by Baidu; gtlds.json `specification_13: false` is wrong |

For all 8, **the CSV is correct for current state**. Consumers wanting a brand-restricted filter must use `annotations.registry_agreement_types`, NOT `specification_13`.

- **Pinning test:** `tests/integration/test_agreements_integrity.py::test_known_brand_status_mismatches_are_pinned` locks the divergent set. New mismatches (or ICANN fixing one of the sources) surface as a test failure with a clear remediation message.
- **README:** new "Interpreting the data" section documents this plus four other semantic nuances (`icann_translation_en`, `tld_unicode`, `delegated: false` retention, `language_code` derivation).
- **No source overrides:** both ICANN sources are preserved verbatim. The divergence is itself information about TLD lifecycle.
