---
title: IDN language coverage: language_code + language_name_en per IDN
summary: CLDR likelySubtags + per-(script, region) overrides + per-TLD overrides; Han-CJK Simplified/Traditional/Taiwan distinctions; langcodes added as dev dep for provenance
created: 2026-05-27
author: Eric Case
tags: [schema, idn, language, cldr, provenance]
---

# IDN language coverage (2026-05-27)

All 151 delegated IDN TLDs now carry `annotations.language_code` (BCP-47) and `annotations.language_name_en` (English). The fields enable the product narrative *"Chinese: 我爱你 ('I love you')"* without forcing consumers to derive language from script.

- **Derivation pipeline** (`src/build/idn_language.py`):
    1. Manual override in `data/manual/annotations.json` (`language_code: "..."`) wins.
    2. `(tld_script, tld_iso)` region table, e.g. `(Cyrillic, bg) → bg`, `(Arabic, ir) → fa`.
    3. `tld_script` default, e.g. `Devanagari → hi`, `Han-CJK → zh`.
    4. Otherwise raise (no silent fallback to a script default for an unmapped script).
- **CLDR provenance.** Script defaults come from Unicode CLDR `likelySubtags` (`und-<Script>.maximize()`). Region overrides mostly match CLDR's `und-<Script>-<Region>.maximize()` with two documented editorial deviations (`(Cyrillic, eu) → bg`, `(Cyrillic, kz) → kk`), both pinned in `tests/build/test_idn_language_provenance.py`.
- **Han-CJK variants.** The 7 Han-CJK ccTLDs each carry an explicit override: `zh-Hans` (`xn--fiqs8s`, `xn--yfro4i67o`), `zh-Hant` (`xn--fiqz9s`, `xn--j6w193g`, `xn--mix891f`), `zh-Hant-TW` (`xn--kprw13d`, `xn--kpry57d`). gTLD brand IDNs in Han-CJK stay on the generic `zh`.
- **Dev dependency:** `langcodes==3.5.1` added (no `language_data`; the 22 MB data package is not needed for `maximize()`). Used only by the provenance test, never by the build path.
- **Integrity:** `tests/integration/test_idn_language_coverage.py` asserts every delegated IDN has both fields. `tests/build/test_idn_language_provenance.py` pins script defaults + region overrides to CLDR.

D-C6's earlier "language is not derivable from current data" verdict ([[2026-05-19 - Typed Graph derivation]]) was reversed by the CLDR-based approach. Schema rationale and trade-offs in [[2026-05-25 - IDN-discovery]].
