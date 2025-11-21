# iana-data

## Overview

[IANA](https://www.iana.org/) publishes some raw, canonical data about the DNS and root zone TLDs. This project is an attempt to make the IANA data easier to explore and interpret.

Here are some of the questions we'd like to be able to answer, from IANA's data:

- How many delegated TLDs are there?
- Of the delegated TLDs, how many are Generic, and how many are Country-Code?
- Of the Country-Code TLDs, how many are the IDN equivalent of an ASCII ccTLD?
- Which countries do the ccTLDs represent?
- How many TLDs are IDNs?
- What do the IDNs mean?
- When was a given TLD delegated?
- Which entity is the manager of a given TLD?
- What are the parent entities of the TLD managers, if any?
- Etc.

## Data files

Here are the data files we're working with:

- The ["All TLDs" txt file](https://data.iana.org/TLD/tlds-alpha-by-domain.txt)
- The [Root DB html file](https://www.iana.org/domains/root/db), which alas doesn't appear to be available in a friendlier format
- The [RDAP "bootstrap" file](https://data.iana.org/rdap/dns.json)
- The individual IANA TLD pages, like [this one for `.beer`](https://www.iana.org/domains/root/db/beer.html)

There are a few challenges with these data files, for example:

For the "All TLDs" text file:

- It doesn't say which are `generic` (gTLDs) vs `country-code` (ccTLDs)
- There are `xn--` IDNs in the file; some are gTLDs, and some are ccTLDs
- All two-character ASCII TLDs are ccTLDs, but not all two-character IDNs are ccTLDs
- All the TLDs in there are delegated, which is handy. E.g. "currently in the DNS"

For the "Root DB" html file:

- It lists more TLDs than the "All TLDs" file, because it also includes some `undelegated` TLDs. (These have a `TLD Manager` value of `Not assigned`.)
- It has more "types" than just `generic` and `country-code` - it also lists `sponsored`, `infrastructure`, and `generic-restricted` types
- It shows the Unicode IDN variants in the rendered html, and their ASCII variants in their `href` links to the per-TLD pages on the IANA website
- We can use the combination of `country-code` and IDN status, to determine which IDNs are ccTLDs vs. gTLDs

For the RDAP bootstrap file:

_FIXME_

## Supplemental data

_FIXME_

## Generated data

### `tlds.json`

The `data/generated/tlds.json` file is an "enhanced" bootstrap file, which aggregates the myriad pieces of related data for a given TLD, into a single file and data structure.

Here is its schema:

```jsonc
{
  // === File Metadata ===
  "description": "string",          // Human-readable description of this file
  "publication": "ISO8601 timestamp", // When this file was published/generated (ISO 8601 with timezone)
  "sources": {
    "iana_root_db": "url",          // URL to IANA Root Zone Database
    "iana_rdap": "url"              // URL to IANA RDAP Bootstrap file
  },

  // === TLD Entries ===
  "tlds": [
    {
      // --- Core IANA-sourced fields (always present) ---
      "tld": "string",                     // ASCII TLD without leading dot (e.g. "com", "xn--flw351e") [REQUIRED]
      "tld_unicode": "string",             // Unicode representation (only for IDNs, e.g. "谷歌") [OPTIONAL - omit if not IDN]
      "tld_iso": "string",                 // ISO 3166-1 alpha-2 ccTLD this IDN is equivalent to (e.g. "cn") [OPTIONAL - IDN ccTLDs only]
      "idn": ["string"],                   // Array of IDN variants of this ccTLD (e.g. ["xn--fiqs8s", "xn--fiqz9s"]) [OPTIONAL - ISO ccTLDs only]
      "delegated": boolean,                // true if TLD Manager is assigned, false if "Not assigned" [REQUIRED]
      "iana_tag": "string",                // IANA tag: "generic" | "country-code" | "sponsored" | "infrastructure" | "generic-restricted" | "test" [REQUIRED]
      "type": "string",                    // Derived type: "gtld" | "cctld" [REQUIRED]

      // --- Organizations ---
      "orgs": {                            // Organizations associated with this TLD [OPTIONAL - omit if undelegated]
        "tld_manager": "string",           // TLD Manager name from IANA Root Zone Database [REQUIRED if orgs present]
        "admin": "string",                 // Administrative Contact organization [OPTIONAL - omit if empty]
        "tech": "string"                   // Technical Contact organization [OPTIONAL - omit if empty]
      },

      // --- Name Servers ---
      "nameservers": ["string"],           // Array of nameserver hostnames (e.g. ["a.gtld-servers.net", "b.gtld-servers.net"]) [OPTIONAL - omit if undelegated]

      // --- Registry Information ---
      "registry_url": "string",            // URL for registration services (e.g. "http://www.verisigninc.com") [OPTIONAL - omit if not present]
      "whois_server": "string",            // WHOIS server hostname (e.g. "whois.verisign-grs.com") [OPTIONAL - omit if not present]
      "rdap_server": "string",             // RDAP server URL (e.g. "https://rdap.verisign.com/com/v1/") [OPTIONAL - omit if no RDAP]

      // --- Dates ---
      "tld_created": "string",             // TLD registration date (YYYY-MM-DD) [OPTIONAL - omit if not present]
      "tld_updated": ["string"],           // TLD record update dates (YYYY-MM-DD), array to track history [OPTIONAL - omit if not present]

      // --- IANA Reports ---
      "iana_reports": [                    // Array of IANA delegation/transfer reports [OPTIONAL - omit if no reports]
        {
          "title": "string",               // Report title
          "date": "string"                 // Report date (YYYY-MM-DD)
        }
      ],

      // --- Annotations (supplemental/derived data) ---
      "annotations": {                     // [OPTIONAL - omit entire object if no annotations]

        // RDAP metadata
        "rdap_source": "string",           // Source of RDAP server: "IANA" for canonical sources, or URL for supplemental sources

        // Geographic metadata (primarily for ccTLDs)
        "country_name_iso": "string",      // ISO 3166 country name (e.g. "Taiwan", "United States")

        // Custom taxonomies
        "tags": ["string"],                // Array of custom tags (e.g. ["brand"], ["geo"])

        // Organizational metadata
        "parent_entity": "string",         // Parent organization of TLD manager

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

It looks like this:

_FIXME - add an example_

## Local usage

- `make deps` - Install the project dependencies
- `make test` - Run all the tests
- `make coverage` - See the test coverage
- `make download-core` - Downloads the three core IANA files, respecting cache headers
- `make download-tld-pages` - Downloads the individual TLD HTML pages
- `make download-tld-pages GROUPS="a b c"` - Specify one or more groups of pages to download, by letter

## Local dev

Dependencies:

- [uv](https://docs.astral.sh/uv/) & [ruff]([ruff](https://docs.astral.sh/ruff/)) - Friendly local tooling
- [httpx](https://github.com/encode/httpx/) - Friendly HTTP usage
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

- [ ] Annotated data - the parent entity of the TLD Manager (grouping them, e.g. Binky Moon -> Identity Digital)
- [ ] GH Actions automation for building `tlds.json`

**Later**

- [ ] Annotation - `brand` TLDs - via https://www.icann.org/en/registry-agreements?page=1&agreement-type=brand-spec-13
- [ ] Annotation - `open` or `closed` TLDs (needs discovery)
- [ ] Annotation - IDN meanings, maybe could derive from the individual TLD web pages
- [ ] Annotation - IDN language
- [ ] Checkly monitoring for cctld rdap servers
- [ ] Curl + make command monitoring, for rdap servers (disabled)
  - [ ] Document this in the readme
- [ ] Script to create a Sqlite db from the data - maybe purely from client side? E.g. JS could generate it "on the fly"?
- [ ] Wikidata - figure out how to programmatically get (some or all of) this data into Wikidata, and Wikipedia
- [ ] Add a `version` field to the `tlds.json` schema?
- [ ] Check other git repos, for TLDs TXT list change history
    - [some txt file history](https://github.com/ris-work/TLD-watch/commits/master/)
    - [Go project](https://github.com/jehiah/generic_tlds/commits/master/)
    - ZoneDB has some history

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
