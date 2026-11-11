# iana-data

## Tl;dr

[IANA](https://www.iana.org/) and [ICANN](https://www.icann.org/) publish a lot of canonical, interesting, and useful _structured_ information about the top-level domain namespace. This project fetches nightly copies of their data, and jams it into a single `data/generated/tlds.json` file so that it's all in a single place.

It's sort of an API-in-a-box, for exploring the TLD cinematic universe. It's _small data_, so this git repo has the change history from each nightly snapshot. For example:

- All top-level domains
- Their ASCII & Unicode IDN variants
- Their ccTLD or gTLD type
- The names of the adminstrative and technical orgs that manage them
- Their DNS nameservers, IPv4 & IPv6 addresses, and associated ASNs and AS orgs
- Their WHOIS and RDAP server URLs
- Their ICANN registry agreement types, e.g. `brand`, etc.
- Etc.

### ccTLD RDAP servers

There are a handful of ccTLD RDAP server URLs that for whatever reason, aren't listed in IANA's RDAP bootstrap file. (Where possible, we include the sources where we found the RDAP URLs, but sometimes it's just from basic guessing)

_Note:_ For folks unfamiliar with this ecosystem, ICANN governs all the gTLDS, and mandates that they offer RDAP servers. ccTLDs - all ~250 of them - are each governed by themselves, and therefore can publish RDAP or WHOIS servers, or not. This dataset attempts to collect the RDAP server URLs.

Since these URLs may change, we have some lightweight monitoring in place to keep an eye on them:

https://cctld-rdap.checkly-dashboards.com/

Later on, we'll work on a friendly UI for all this.

## Background

IANA publishes some raw, canonical data about the DNS and root zone TLDs. This project is an attempt to make the data easier to explore and interpret.

Here are some of the questions we'd like to be able to answer, from the IANA data:

- How many delegated TLDs are there?
- Of the delegated TLDs, how many are Generic, and how many are Country-Code?
- Which countries do the ccTLDs represent?
- How many TLDs are IDNs?
- What do the IDNs mean?
- Of the Country-Code TLDs, how many are the IDN equivalent of an ASCII ccTLD?
- When was a given TLD delegated?
- Which entity is the manager of a given TLD?
- What are the parent entities of the TLD managers, if any?
- Which TLDs are "Brand" TLDs, and not open for general registration?
- Etc.

## Data files

Here are the data files we're working with:

- IANA - The [All TLDs text file](https://data.iana.org/TLD/tlds-alpha-by-domain.txt)
- IANA - The [TLD JSON file](https://data.iana.org/TLD/v1/tlds.json), the machine-readable export of the [Root Zone Database](https://www.iana.org/domains/root/db), with its [schema](https://data.iana.org/TLD/v1/tlds-schema.json)
- IANA - The [RDAP bootstrap file](https://data.iana.org/rdap/dns.json)
- ICANN - The [Registry Agreements table CSV](https://www.icann.org/en/registry-agreements), which help us identify which are Brand TLDs, etc.
- IPtoASN - [Public Domain-licensed data](https://iptoasn.com/) that maps IP ranges to their AS orgs and countries. This lets us see which ASNs are used for which sets of Nameserver IPs, for example.

## Working with the data files

There are a few challenges with these data files, for example:

**For the "All TLDs" text file:**

- It doesn't say which are `generic` (gTLDs) vs `country-code` (ccTLDs)
- There are `xn--` IDNs in the file; some are gTLDs, and some are ccTLDs
- All two-character ASCII TLDs are ccTLDs, but not all two-character IDNs are ccTLDs
- All the TLDs in there are delegated, which is handy. E.g. "currently in the DNS"

**For the TLD JSON file:**

- It lists more TLDs than the "All TLDs" file, because it also includes TLDs that are not delegated: `retired`, `eligible` and `reserved`
- Its `type` is one of `generic`, `country-code`, `special-use` or `test`. The older `sponsored`, `infrastructure` and `generic-restricted` values are gone, and we keep them under `archived.iana_tag`
- It carries the Unicode label, the script, and for IDN ccTLDs the ISO 3166-1 code of the country
- It carries the manager, the administrative and technical contacts, the nameservers with their addresses, and the DS records
- It no longer carries a TLD's creation date. We keep the dates we had in `data/manual/tld-archive.json`
- `data/source/archive/` holds the last Root Zone Database HTML pages, which carried this data before IANA published the JSON file

**For the RDAP bootstrap file:**

- All the gTLDs are listed
- Some ccTLDs are listed
- A lot of ccTLDs aren't listed
- Some TLDs have the same RDAP server URL
- Etc.

**For the ICANN Registry Agreements CSV:**

- It has Agreement Types, which include the Brand agreements
- There's other stuff that may be relevant in the future

## Supplemental data

- The `data/manual/supplemental-cctld-rdap.json` file is the manually-edited list of ccTLD servers that aren't in the IANA file. Ideally, we'll find more, and add them here.
- The `data/generated/metadata.json` file keeps track of our lifecycle of http fetches. `last_checked` moves every time a source is polled; `last_downloaded` moves only when new content reached the published data. For `IPTOASN`, the nightly stamps `last_checked` after its build and moves `last_downloaded` only when that build consumed the artifact; a direct `--download-iptoasn` stamps both at download time. That entry also carries `run_id`, the GitHub Actions run of `update-iptoasn.yaml` that produced the artifact its `last_downloaded` refers to.
- The `data/generated/idn-script-mapping.json` file maps IDNs to their Scripts, e.g. Arabic, Cyrillic, etc. This isn't the same as a TLD's language, but it's close enough, and it's canonical data from the Unicode strings.

## `tlds.json`

The `data/generated/tlds.json` file is an "enhanced" bootstrap file, which aggregates the myriad pieces of related data for a given TLD, into a single file and data structure.

The file includes both currently-delegated TLDs and previously-delegated TLDs that have since been removed from the root (retired brand gTLDs, dissolved-country ccTLDs, etc.). Filter on `delegated == true` for the current live set.

Here is its schema:

```jsonc
{
  // === File Metadata ===
  "description": "string",          // Human-readable description of this file
  "publication": "ISO8601 timestamp", // When this file was published/generated (ISO 8601 with timezone)
  "sources": {
    "iana_tlds": "url",             // URL to the IANA TLD JSON file
    "iana_rdap": "url"              // URL to IANA RDAP Bootstrap file
  },

  // === TLD Entries ===
  "tlds": [
    {
      // --- Core IANA-sourced fields (always present) ---
      "tld": "string",                     // ASCII TLD without leading dot (e.g. "com", "xn--flw351e") [REQUIRED]
      "tld_unicode": "string",             // Unicode representation (only for IDNs, e.g. "谷歌") [OPTIONAL - omit if not IDN]
      "tld_script": "string",              // Unicode script name for IDNs (e.g. "Han-CJK", "Arabic", "Cyrillic") [OPTIONAL - IDNs only]
      "tld_script_code": "string",         // IANA's ISO 15924 script code for the label (e.g. "Latn", "Hani") [REQUIRED]
      "tld_iso": "string",                 // ISO 3166-1 alpha-2 ccTLD this IDN is equivalent to (e.g. "cn") [OPTIONAL - IDN ccTLDs only]
      "idn": ["string"],                   // Array of IDN variants of this ccTLD (e.g. ["xn--fiqs8s", "xn--fiqz9s"]) [OPTIONAL - ISO ccTLDs only]
      "status": "string",                  // IANA status: "active" | "retired" | "eligible" | "reserved" [REQUIRED]
      "delegated": boolean,                // true exactly when status is "active"; every other record is retained with false [REQUIRED]
      "iana_tag": "string",                // IANA type: "generic" | "country-code" | "special-use" | "test" [REQUIRED]
      "type": "string",                    // Derived type: "gtld" | "cctld" | "special-use" ("test" derives "gtld") [REQUIRED]
      "archived": {                        // Values IANA no longer publishes [OPTIONAL - omit if none]
        "iana_tag": {
          "value": "string",               // The former tag: "sponsored" | "generic-restricted" | "infrastructure"
          "archived_on": "string"          // Date we archived it (YYYY-MM-DD)
        }
      },

      // --- Organizations (canonical data, nested by source) ---
      "orgs": {                            // Organizations associated with this TLD [OPTIONAL - omit if undelegated]
        "iana": {                          // Roles per the IANA TLD JSON [OPTIONAL - omit if none]
          "sponsor": "string",             // Sponsoring Organisation (TLD Manager) [REQUIRED if iana present]
          "admin": "string",               // Administrative Contact organization [OPTIONAL - omit if empty]
          "tech": "string"                 // Technical Contact organization [OPTIONAL - omit if empty]
        },
        "icann": {                         // Fields from the ICANN gTLDs Report [OPTIONAL - gTLDs only, omit otherwise]
          "registry_operator": "string",   // Registry Operator name [null if no active contract]
          "specification_13": boolean,     // .Brand TLD flag (Specification 13). Application-era; see "Interpreting the data" [null if no active contract]
          "third_or_lower_level_registration": boolean, // true only for .museum/.name/.pro [null if no active contract]
          "application_id": "string",      // ICANN new-gTLD application ID [null if not applicable]
          "registry_operator_country_code": "string", // ISO country code of the operator [null if absent]
          "date_contract_signed": "string", // Registry Agreement signature date (YYYY-MM-DD) [null if absent]
          "date_delegated": "string",      // Root-zone delegation date (YYYY-MM-DD; 1985-01-01 backfill = pre-ICANN legacy) [null if absent]
          "contract_terminated": boolean,  // true if the Registry Agreement was terminated [always present]
          "date_removed": "string"         // Root-zone removal date (YYYY-MM-DD); pairs with contract_terminated [null if active]
        }
      },

      // --- DS Records ---
      "ds_records": [                      // DS records in the root zone [OPTIONAL - omit if undelegated or unsigned]
        {
          "key_tag": number,
          "algorithm": number,             // DNSSEC algorithm number
          "digest_type": number,           // DS digest type
          "digest": "string"               // Lower-case hexadecimal
        }
      ],

      // --- Name Servers ---
      "nameservers": [                     // Array of nameserver objects [OPTIONAL - omit if undelegated]
        {
          "hostname": "string",            // Nameserver hostname (e.g. "a.gtld-servers.net") [REQUIRED]
          "ipv4": [                        // IPv4 address objects [REQUIRED - may be empty array]
            {
              "ip": "string",              // IPv4 address (e.g. "192.5.6.30") [REQUIRED]
              "asn": number,               // AS number (e.g. 36619), 0 for "not routed" [REQUIRED]
              "as_org": "string",          // AS organization name (e.g. "VERISIGN-INC") [REQUIRED]
              "as_country": "string"       // AS country code (e.g. "US"), "None" if not assigned [REQUIRED]
            }
          ],
          "ipv6": [                        // IPv6 address objects, normalized [REQUIRED - may be empty array]
            {
              "ip": "string",              // IPv6 address, compressed (e.g. "2001:503:a83e::2:30") [REQUIRED]
              "asn": number,               // AS number (e.g. 36619), 0 for "not routed" [REQUIRED]
              "as_org": "string",          // AS organization name (e.g. "VERISIGN-INC") [REQUIRED]
              "as_country": "string"       // AS country code (e.g. "US"), "None" if not assigned [REQUIRED]
            }
          ]
        }
      ],

      // --- Registry Information ---
      "registry_url": "string",            // URL for registration services (e.g. "http://www.verisigninc.com") [OPTIONAL - omit if not present]
      "whois_server": "string",            // WHOIS server hostname (e.g. "whois.verisign-grs.com") [OPTIONAL - omit if not present]
      "rdap_server": "string",             // RDAP server URL (e.g. "https://rdap.verisign.com/com/v1/") [OPTIONAL - omit if no RDAP]

      // --- Dates ---
      "tld_created": "string",             // TLD registration date (YYYY-MM-DD), from data/manual/tld-archive.json; absent for a TLD delegated after 2026-09-28 [OPTIONAL]
      "tld_updated": ["string"],           // TLD record update dates (YYYY-MM-DD), array to track history [OPTIONAL - omit if not present]
      "events": {                          // IANA's recorded events [OPTIONAL - omit if none; each key omitted if not recorded]
        "delegation": "string",            // When the TLD was delegated (YYYY, YYYY-MM or YYYY-MM-DD)
        "revocation": "string"             // When the TLD was removed from the root zone (same precision)
      },

      // --- Special-use names ---
      "purpose": "string",                 // Why the name is reserved or set aside [OPTIONAL - special-use only]
      "remarks": "string",                 // IANA's explanatory text, in Markdown [OPTIONAL - special-use only]

      // --- Annotations (supplemental/derived/non-canonical data) ---
      "annotations": {                     // [OPTIONAL - omit entire object if no annotations]

        // Canonical org resolution (each registry org position resolved against
        // organizations.json). Emitted when the raw org value resolves to a record
        // there: *_alias is the human display_name, *_slug is the stable FK.
        "iana_sponsor_alias": "string",            // Sponsoring org display_name [OPTIONAL]
        "iana_sponsor_slug": "string",             // FK into organizations.json [OPTIONAL]
        "iana_admin_alias": "string",              // Administrative contact org display_name [OPTIONAL]
        "iana_admin_slug": "string",               // FK into organizations.json [OPTIONAL]
        "iana_tech_alias": "string",               // Technical contact org display_name [OPTIONAL]
        "iana_tech_slug": "string",                // FK into organizations.json [OPTIONAL]
        "icann_registry_operator_alias": "string", // Registry Operator display_name [OPTIONAL - gTLDs]
        "icann_registry_operator_slug": "string",  // FK into organizations.json [OPTIONAL - gTLDs]

        // RDAP metadata
        "rdap_source": "string",           // Source of RDAP server: "IANA" (canonical) or "supplemental" (from data/manual/supplemental-cctld-rdap.json)

        // Geographic metadata (derived from ISO 3166)
        "country_name_iso": "string",      // ISO 3166 country name (e.g. "Taiwan", "United States")

        // Geographic scope (ccTLDs derive "country"; the rest are hand-curated in data/manual/annotations.json)
        "geographic_scope": "string",      // "city" | "subdivision" | "country" | "supranational" [OPTIONAL - omit if not applicable]

        // Cultural affiliation (hand-curated, from data/manual/annotations.json)
        "cultural_affiliation": "string",  // Culture slug (e.g. "basque", "arab") [OPTIONAL - omit if none]

        // ICANN Registry Agreement metadata (gTLDs only)
        "registry_agreement_types": ["string"], // Array of agreement types: "base" | "brand" | "community" | "sponsored" | "non_sponsored"
        "icann_translation_en": "string",  // ICANN's raw English Translation of an IDN label, source-faithful [OPTIONAL - IDN gTLDs only]

        // IANA's own annotations, verbatim
        "iana_translation_en": "string",   // IANA's English meaning of an IDN label [OPTIONAL - IDNs]
        "iana_transliteration": "string",  // IANA's romanization of an IDN label [OPTIONAL - IDNs]
        "iana_delegation_round": "string", // "pre-icann", or the year the application round opened [OPTIONAL - gTLDs]

        // IDN language metadata. IANA's tag, unless ours refines it; ours alone when IANA has none
        "language_code": "string",         // BCP-47 code (e.g. "ar", "hi", "zh-Hant-TW") [OPTIONAL - IDN only]
        "language_name_en": "string",      // English name (e.g. "Arabic", "Hindi", "Chinese (Taiwan)") [OPTIONAL - IDN only]
        "language_code_source": "string",  // "IANA" | "refined" | "derived" [OPTIONAL - IDN only]

        // AS Org infrastructure operators (resolved against organizations.json)
        "as_org_aliases": ["string"],      // Canonical DNS provider display_names hosting nameservers (e.g. ["Identity Digital", "VeriSign"])
        "as_org_slugs": ["string"],        // FKs into organizations.json, parallel to as_org_aliases

        // General notes
        "notes": [                         // Array of timestamped notes
          {
            "date": "ISO8601 date",        // Date of note (YYYY-MM-DD)
            "note": "string"               // Note content
          }
        ]
      }
    }
  ]
}
```

## Identifiers: A-labels vs Unicode

Every TLD is identified by its **A-label**: the ASCII form, including `xn--` punycode for IDNs (e.g. `xn--80adxhks`). The A-label is the canonical key and the only form used for joins and references: the `tld` field, per-TLD filenames, the index keys, and every TLD in `organizations.json` `roles`. A-labels are stable and unambiguous (the U-label depends on Unicode normalization and IDNA version), which keeps cross-file joins exact.

The **U-label** (the rendered Unicode form, e.g. `москва`) is display-only and appears solely in the `tld_unicode` field, alongside the A-label, never as a key or reference. Consumers that render a name resolve the A-label to `tld_unicode`; they never key on it.

## Interpreting the data

A handful of fields look obvious but carry semantic nuance worth knowing before you build on them.

### `specification_13` is application-era, not current state

`orgs.icann.specification_13` reflects whether the TLD was granted **Specification 13 (.Brand) status at delegation**. It is set when the registry agreement is signed and **persists in the ICANN data**, even if the brand owner later changes Brand status.

For a **currently-restricted-to-brand** filter, use the CSV-derived field instead:

```python
is_currently_brand = "brand" in tld["annotations"].get("registry_agreement_types", [])
```

The CSV (`annotations.registry_agreement_types`) reflects the **current contract**; it updates when the agreement type changes. ICANN's `specification_13` flag does not.

Today the two sources disagree on 8 delegated gTLDs (`baidu`, `case`, `diy`, `food`, `gmo`, `monster`, `nexus`, `sbs`); the set is pinned by `tests/integration/test_agreements_integrity.py::test_known_brand_status_mismatches_are_pinned` so future drift surfaces as a test failure.

### `icann_translation_en` is source-faithful, not curated

The Translation column from ICANN's registry-agreement CSV is preserved **verbatim**: typos (`大众汽车` → "volkswagon"), romanizations (`谷歌` → "google"), and place names (`москва` → "moscow") are kept as ICANN published them. About 70% are real semantic translations; the rest are transliterations or brand romanizations. There is no curated-meaning layer.

For a clean "this TLD means X in English" narrative, combine `icann_translation_en` with `language_name_en` and let the reader judge from `tld_unicode`. Or filter to TLDs where `iana_tag == "generic"` and `specification_13` is false (most likely to be real translations).

### `tld_unicode` is IANA's U-label

`tld_unicode` is the `ulabel` IANA publishes for each IDN. It is copied, not computed.

### `delegated: false` records are retained in `tlds.json`

Every record IANA lists stays in `tlds.json`, and `delegated` is true only for `status: "active"`. As of 2026-11-10 that is 1,603 records: 1,436 active, 154 retired (removed gTLDs, dissolved-country ccTLDs such as `.an` and `.yu`, and the IANA test TLDs), 5 eligible ccTLDs that are not delegated, and 8 reserved special-use names such as `.local` and `.onion`. **Filter on `delegated: true`** for the current live set; the retention is deliberate so removal dates and the original record stay queryable.

A reserved name has no organizations, nameservers or dates. It carries `purpose` and `remarks` instead.

### `iana_tag` values IANA dropped are kept under `archived`

IANA used to tag 14 TLDs `sponsored`, 3 `generic-restricted` and `.arpa` `infrastructure`. It now publishes `generic` for the first 17 and `special-use` for `.arpa`. Each of those 18 records keeps its former value at `archived.iana_tag`, with the date we archived it.

### `language_code` prefers IANA's tag

IANA publishes a BCP-47 `language_code` for most IDNs. We use it, with one exception: when our own value extends IANA's with a subtag (IANA says `zh`, ours says `zh-Hant-TW`), ours is kept. `language_code_source` records which happened: `IANA`, `refined`, or `derived` when IANA has no tag.

Our own value comes from `tld_script` via Unicode CLDR `likelySubtags`, with per-(script, region) overrides for ccTLDs and per-TLD overrides in `data/manual/annotations.json`. See `src/build/idn_language.py` for the rules and `tests/build/test_idn_language_provenance.py` for the CLDR provenance check.

### Stability

This data has no versioned releases or changelog yet. Field names and values can change without notice while the model settles, so pin to a commit if you depend on a particular shape.

## The typed graph

Alongside `tlds.json`, the build ships four derived reverse-index artifacts that model the root zone as a typed graph of four entity types plus one enum:

- **Domains**: the TLDs themselves (`tlds.json`).
- **Organizations**: registries, governance bodies, and infrastructure operators (`organizations.json`).
- **Places**: countries, dependent territories, subdivisions, cities, and supranational regions (`places.json`).
- **Cultures**: ethno-linguistic communities like the Basques or Welsh (`cultures.json`).
- **Agreement types**: the ICANN registry-agreement enum (`agreements.json`).

Each TLD relates to one or more Organizations through _roles_ (Sponsor, Administrative Contact, Technical Contact, and ICANN Registry Operator for gTLDs), to zero or more Places (most ccTLDs map to one country; geographic gTLDs map to a city, subdivision, country, or supranational region), to an optional Culture, and to its agreement types. Each derived artifact is a deterministic reverse index of `tlds.json`: delete it and `./bin/build --preserve-asn` rebuilds it. Every cross-file relationship is enforced by referential-integrity tests, so a foreign key can never dangle. Records are not orphaned either, with one deliberate exception: an organization whose only names are ASN labels — seeded in `source_names.asn`, retired into `archived.asn`, or both — keeps its record when none of them matches the current TLD data, so it carries no `roles` until a label matches again or a curator resolves it.

## `organizations.json`

The `data/generated/organizations.json` file is the canonical record of the organizations that play roles for TLDs, with a reverse-index of those roles. It is built from a hand-curated identity seed (`data/manual/organizations.json`) joined against `tlds.json`, and replaces the old per-role alias files.

Each org carries an editorial `display_name` and a stable kebab-case `slug` (the foreign key the `tlds.json` annotations point at via `*_slug`), the verbatim `source_names` each source records (grouped `iana` / `icann` / `asn`), an optional `archived` block, hand-added `aliases`, a `homepage`, and a generated `roles` reverse-index grouped by source (absent when nothing currently resolves): `iana.{sponsor,admin,tech}`, `icann.{registry_operator}`, `asn.{operator}`. Entity type and TLD counts are derivable from `roles`, so they are not stored. `orgs[]` is sorted by `slug`.

Four fields make a raw string resolve to an org, and they differ in scope:

| Field                   | Resolves in       | Asserted against live data |
| ----------------------- | ----------------- | -------------------------- |
| `source_names.<source>` | that source only  | yes, for `iana` / `icann`  |
| `archived.<source>`     | that source only  | never                      |
| `display_name`          | all three sources | never                      |
| `aliases`               | all three sources | never                      |

`archived` holds names previously curated for one source that no longer match any raw value there, as `{"name": ..., "archived_on": "YYYY-MM-DD"}`. It is absent when an org has archived nothing. `archived_on` is **the date the entry was written into the archive**, not a last-seen date: the snapshot that reveals a label's absence is by definition one where it has already gone. Archiving a name from `source_names.<source>` keeps its scope exactly as it was and never removes it, so attribution survives; what changes is that it stops being asserted. Migrating an alias into the archive is the case that narrows, since an alias resolved in all three sources. Either way an archived name may still resolve elsewhere through `display_name` or an alias, because the archive only controls its own source's contribution. Entries are not promoted back out — an ASN label that returns resolves identically where it is, and moving it back re-arms the drift it caused. `aliases` are alternate names that resolve everywhere, for orgs recorded under different spellings across sources.

> **Consolidated subset:** this currently covers the curated multi-source organizations only. The single-source long tail (orgs that appear under one exact name in one source) is not yet included, so the absence of a TLD's operator here does not mean it has none.

## `places.json`

The `data/generated/places.json` file is the canonical record of the places associated with TLDs, with a reverse-index of their TLDs. Countries are derived mechanically from ccTLDs (ISO 3166-1 via `pycountry`); subdivisions, cities, and supranational regions come from a hand-curated seed (`data/manual/places.json`).

Each place carries a stable `slug` (ISO 3166-1 alpha-2 for countries, e.g. `gb`; a recognizable short name for subdivisions, e.g. `basque-country`; the TLD for cities, e.g. `amsterdam`), an English `name_en`, a `subtype` (`country` / `subdivision` / `city` / `supranational`), the `iso_code` where one exists, a `parent` slug for hierarchy (subdivision/city → country; dependent territory → sovereign), an optional `info_link`, and the `tlds` reverse index. A sparse `iso_designation` field carries ISO 3166-1 status for the special cases: `dependent_territory` (e.g. `bm` → `gb`), `exceptionally_reserved` (`ac`), `transitionally_reserved` (`su`), and `special_area` (`aq`). `places[]` is sorted by `slug`.

The United Kingdom is one place slugged `gb` (its ISO alpha-2), carrying both `.gb` and `.uk`; IDN ccTLDs fold into their country (e.g. `xn--p1ai` joins `ru`). Slugs and `tlds` are A-labels/ASCII; Unicode rendering is left to consumers.

## `cultures.json`

The `data/generated/cultures.json` file records the ethno-linguistic communities that at least one TLD claims affiliation with, with a reverse-index of their TLDs. It is built from a hand-curated seed (`data/manual/cultures.json`) joined against each TLD's `cultural_affiliation` annotation.

Each culture carries a stable `slug` (the foreign key `cultural_affiliation` points at), an English `name_en`, an `info_link` to Wikipedia, an optional BCP-47 `language_code` (`null` for multi-lingual cultures like `swiss` / `desi` / `kiwi` / `scottish`), and the `tlds` reverse index. `cultures[]` is sorted by `slug`. The schema is intentionally minimal: descriptions and cross-artifact links belong on the canonical source (Wikipedia via `info_link`), not duplicated here.

## `agreements.json`

The `data/generated/agreements.json` file is the ICANN registry-agreement-type enum with a reverse-index of the gTLDs under each. Each record carries a canonical `slug` (`base` / `non_sponsored` / `brand` / `community` / `sponsored`), a friendly `display_name`, the verbatim ICANN string under `source_names.icann`, and the `tlds` reverse index. `agreements[]` is sorted by `slug`.

## Local usage

- `make deps` - Install the project dependencies
- `make test` - Run all the tests
- `make coverage` - See the test coverage

**Data downloads**

- `make download-core` - Downloads the core IANA files, respecting cache headers. The TLD JSON is parsed before it replaces the stored copy; a rejected or failed download keeps the previous file

**Misc**

- `make analyze-idn-scripts` - analyzes the IDNs, and prints their associated Unicode label names
- `make generate-idn-mapping` - creates the `data/generated/idn-script-mapping.json` file, by mapping IDNs like `ελ` to their Unicode character labels (e.g. `GREEK`), then using `pycountry` to map their labels to their ISO script names
- `make analyze-registry-agreements` - summarizes the contents of the ICANN Registry Agreements file

## Local dev

Dependencies:

- [uv](https://docs.astral.sh/uv/) & [ruff]([ruff](https://docs.astral.sh/ruff/)) - Friendly local tooling
- [httpx2](https://github.com/pydantic/httpx2/) - Friendly HTTP usage
- [tenacity](https://github.com/jd/tenacity) - Friendly HTTP retries
- [selectolax](https://github.com/rushter/selectolax) - HTML parsing
- [pyright](https://github.com/microsoft/pyright) - Type checking
- [pytest](https://github.com/pytest-dev/pytest/) - Testing & coverage framework
- [pycountry](https://github.com/pycountry/pycountry/) - ISO 3166 country code name mapping

## Misc

**ISO 3166-1 alpha-2 country names**

- [Wikipedia details](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2)
- We need to special-case a few:
  - `.ac` - Ascension Island
  - `.eu` - European Union
  - `.su` - Soviet Union
  - `.uk` - United Kingdom

## Todo

### Current

- [ ] Email alerts, similar to Pushover
- [ ] TLDs summary (delegated, gtld/cctld, IDNs, brands, etc.) in the Readme, via GH Actions auto-update
- [ ] Zone file sizes - maybe via the [ICANN Monthly Registry Reports](https://www.icann.org/resources/pages/xbox-2015-10-01-en)?
  - `activity` csv - has interesting data, e.g.
    - `dns-udp-queries-received`
    - `dns-udp-queries-responded`
    - `dns-tcp-queries-received`
    - `dns-tcp-queries-responded`
    - `rdap-queries`
  - `transactions` csv - `totals-domains` column -> `Totals` row has the total for the given month

### Later

- [ ] Add provenance (`source` URLs) for the remaining `null`-source alias entries in `data/manual/organizations.json`. Currently only the non-obvious lineage merges cite a source.
- [ ] Continue canonicalising the long tail of `tld_manager` and `orgs.iana.tech` operator names (mostly ccTLD/NIC operators and dotBrand corporates). `scripts/analyze_operators.py` ranks the unaliased candidates.
- [ ] Annotation - IDN meanings & language, maybe could derive from the individual TLD web pages?
- [ ] Annotation - `open` or `closed` TLDs (needs discovery; may be addressed by the `brand` registry type annotation?)
- [ ] Script to create a Sqlite db from the data - maybe purely from client side? E.g. JS could generate it "on the fly"?
- [ ] Wikidata contribution - figure out how to programmatically get (some or all of) this data into Wikidata, and / or Wikipedia
- [ ] Add a `version` field to the `tlds.json` schema?
- [ ] PeeringDB API script (or integration of some sort), for deriving AS Org alias names
- [ ] Data integrity - more e2e tests to confirm that the data all lines up. E.g. the TLD pages <-> RDAP bootstrap file <-> full root db html page contents
- [ ] Check other git repos, for TLDs TXT list change history
  - [some txt file history](https://github.com/ris-work/TLD-watch/commits/master/)
  - [Go project](https://github.com/jehiah/generic_tlds/commits/master/)
  - ZoneDB has some history

**If anyone asks**

- [ ] ccTLD RDAP - `curl` workfow for the monitoring, in addition to the Checkly config
- [ ] More data from the TLD pages, e.g. IANA Report link URLs

**Done**

- [x] Basic CLI
- [x] File downloads, adhere to cache, etc. headers (be a good citizen)
- [x] Downloads for core files - Metadata file for tracking last-downloaded dates, header values, etc.
- [x] Tests, fixtures, test coverage, linting
- [x] Enhanced Bootstrap file (`tlds.json`) - Data structure, build functionality
- [x] Integration tests - Data accuracy, integrity, and overlap tests
- [x] Downloads for individual TLD pages
- [x] IDN & ISO ASCII equivalent TLD mappings
- [x] CI for tests
- [x] CI for data updates
- [x] Added automated ISO-3166 country names support, via a canonical & trustworthy data source
- [x] Added IDN -> script mapping, e.g. to identify IDNs as Arabic, CJK, etc
- [x] Added ICANN Registry Agreements CSV, to identify `brand` TLDs
- [x] Annotation - `brand` TLDs identification via the ICANN CSV
- [x] Schedule for downloading the ICANN CSV (monthly)
- [x] Checkly monitoring for ccTLD RDAP servers
- [x] TLD Manager "aliases" per the `data/manual/tld-manager-aliases.json` file
- [x] `tlds.json` is now in source control
- [x] GH Actions automation for building `tlds.json`
- [x] Nameserver IP addresses (IPv4 and IPv6) added to `tlds.json`
- [x] Added AS Org aliases
