# IANA TLD JSON as the canonical source

Branch: `iana-tlds-json`.

## Why

IANA redesigned the Root Zone Database index and every per-TLD page. Both HTML parsers broke, and the
nightly `update-data` job has failed since 2026-09-29. IANA now publishes the same data as JSON at
`https://data.iana.org/TLD/v1/tlds.json`, with a schema and a `specversion`.

This plan moves the project to that file, deletes the HTML pipeline, and records the data-model
decisions the move forces.

## Evidence

Compared on 2026-11-10 across the 1593 TLDs present in both the JSON and `data/generated/tlds.json`
(built 2026-09-28, commit `644440d3`).

| Our field           | JSON field                    | Differences | Cause                                              |
| ------------------- | ----------------------------- | ----------- | -------------------------------------------------- |
| `delegated`         | `status == "active"`          | 2           | `helsinki`, `juniper` retired in October           |
| `tld_unicode`       | `ulabel`                      | 0           |                                                    |
| `tld_iso`           | `iso3166_code`                | 0           | After lowercasing; the JSON value is uppercase     |
| `orgs.iana.sponsor` | `manager.organization`        | 11          | Real changes; embedded newlines now spaces         |
| `orgs.iana.admin`   | `contacts.admin.organization` | 27          | Same, plus HTML parser bugs (address read as org)  |
| `orgs.iana.tech`    | `contacts.tech.organization`  | 85          | Mostly Identity Digital renames                    |
| `nameservers`       | `nameservers`                 | 14          | Real changes; JSON key is `name`, ours `hostname`  |
| `whois_server`      | `whois_server`                | 6           | Real changes                                       |
| `registry_url`      | `registration_url`            | 6           | Real changes                                       |
| `rdap_server`       | `rdap_base_urls[0]`           | 141         | 140 trailing `/` only; `bh` changed server         |
| `tld_updated`       | `last_updated`                | 367         | Stale data; JSON is a nullable scalar, ours a list |
| `iana_tag`          | `type`                        | 18          | IANA dropped three values                          |
| `tld_created`       | none                          | all         | Gone from every IANA source                        |

Record set: the JSON has 1603 names. Ten are new to us (8 `reserved` special-use names, plus retired
`yu` and `zr`). Two of ours are absent (`emerson`, `xn--4gq48lf9j`).

## Decisions

Agreed with Eric on 2026-11-10.

1. **Source.** The JSON is the only IANA TLD source. The index parser, the per-TLD page parser and the
   page downloader are deleted.
2. **`delegated`** is `status == "active"`.
3. **`iana_tag`** takes IANA's four current values: `generic`, `country-code`, `special-use`, `test`.
4. **Archived `iana_tag`.** The old `sponsored` (14), `generic-restricted` (3) and `infrastructure`
   (1) values are kept per TLD under `archived.iana_tag`, shaped `{"value", "archived_on"}`.
   `archived_on` is the date we archived the value. Unknown keys are errors and dates must be real,
   as in `organizations.json`.
5. **`tld_created`** stays at the top level. Its values come from the archive seed, because no live
   source carries them. A TLD delegated after 2026-09-28 has none.
6. **Archive seed.** `data/manual/tld-archive.json`, extracted once from commit `644440d3`.
7. **`.arpa`** has `iana_tag: "special-use"`. The derived `type` enum becomes
   `gtld | cctld | special-use`. This reading of the decision needs confirmation.
8. **Reserved rows.** The 8 `reserved` special-use names are included, with `delegated: false`.
9. **`emerson` and `xn--4gq48lf9j`** are dropped. ICANN shows both were never delegated, and 13
   sibling gTLDs in the same state are already absent. **Reopened by review:** `agreements.json` is
   built from the TLD records, so both leave it too. See "Review outcome".
10. **`language_code`.** One field. Our value wins when it refines IANA's (starts with IANA's tag plus
    `-`); otherwise IANA's; otherwise our derived value. `annotations.language_code_source` is
    `IANA`, `refined` or `derived`.
11. **Translation.** `annotations.icann_translation_en` is unchanged. IANA's values are added beside
    it, verbatim, with no merge.
12. **Script.** IANA's ISO 15924 code is added for every record. `tld_script` and its pipeline are
    unchanged. A test checks the two agree.
13. **New JSON fields are adopted**: status, DS records, events, delegation round, transliteration,
    purpose, remarks.
14. **Live source files have no date prefix.** The source is `data/source/iana-tlds.json`, with
    `data/source/iana-tlds-schema.json` beside it. The nightly job overwrites both in place.
15. **Fixtures are date-prefixed**, `yyyy-mm-dd-{slug}`, where the date is the capture date. Tests
    use the fixture with the latest date for a slug, through one test helper. A changed upstream
    format gets a new dated fixture and the old one stays.
16. **Old HTML files are kept** as frozen history under `data/source/archive/`, with their
    first-capture dates as prefixes. Frozen files are the only dated files outside the fixtures.
17. **Other sources keep their names** in this branch (`iana-rdap.json`, `iana-tlds.txt`, the ICANN
    files, `iptoasn`).

## Proposed field names

Proposed, not yet confirmed by Eric. These are the names for decision 13 and the additions in 10 to 12.

| JSON field                     | Proposed field in `tlds.json`       | Present on           |
| ------------------------------ | ----------------------------------- | -------------------- |
| `status`                       | `status`                            | All records          |
| `script_code`                  | `tld_script_code`                   | All records          |
| `ds_records`                   | `ds_records`                        | Delegated and signed |
| `events.delegation`            | `events.delegation`                 | Where recorded       |
| `events.revocation`            | `events.revocation`                 | Where recorded       |
| `purpose`                      | `purpose`                           | Special-use records  |
| `remarks`                      | `remarks`                           | Special-use records  |
| `annotations.delegation_round` | `annotations.iana_delegation_round` | gTLDs                |
| `annotations.transliteration`  | `annotations.iana_transliteration`  | IDNs                 |
| `annotations.translation`      | `annotations.iana_translation_en`   | IDNs                 |

## Old files and their new names

| Today                                    | Renamed to                                          |
| ---------------------------------------- | --------------------------------------------------- |
| `data/source/iana-root.html`             | `data/source/archive/2025-11-16-iana-root.html`     |
| `data/source/tld-pages/`                 | `data/source/archive/2025-11-18-iana-tld-pages/`    |
| `tests/fixtures/source/core/root.html`   | `tests/fixtures/source/core/2025-11-18-root.html`   |
| `tests/fixtures/source/core/root-*.html` | `tests/fixtures/source/core/2025-11-29-root-*.html` |
| `tests/fixtures/source/tlds/`            | `tests/fixtures/source/2025-11-18-tlds/`            |

Each date is the first commit at that path, from `git log --diff-filter=A`.

## Consumers of the HTML sources

Every reader below must move to the JSON records or be deleted.

| Reader                                                             | Reads                                 | Used for                                  |
| ------------------------------------------------------------------ | ------------------------------------- | ----------------------------------------- |
| `src/build/tlds.py`                                                | Index and per-TLD pages               | The build                                 |
| `src/build/organizations.py`                                       | `_SOURCES` names `iana-root.html`     | Provenance string in `organizations.json` |
| `src/utilities/download.py`, `src/cli.py`, `src/parse/__init__.py` | Index, to list pages to fetch         | Download and change detection             |
| `src/analyze/root_db_html.py`                                      | Index                                 | `--analyze` report                        |
| `src/analyze/asn_health.py`                                        | Per-TLD pages, by `rglob`             | Tonight's nameserver IPs for the ASN gate |
| `bin/check-asn-drift.py`                                           | Per-TLD pages                         | ASN drift check                           |
| `scripts/idn_unicode_scripts/generate_idn_script_mapping.py`       | Index                                 | Run by `bin/build` and the nightly        |
| `scripts/analyze_nameserver_ips.py`                                | Per-TLD pages                         | Ad hoc analysis                           |
| `tests/integration/test_source_drift.py`                           | Index                                 | Drift against `iana-tlds.txt`             |
| `tests/integration/test_build_reconciliation.py`                   | Index                                 | Build against source                      |
| `tests/integration/test_data_integrity.py`                         | Index                                 | Four integrity tests                      |
| `tests/build/test_tlds.py`                                         | Index                                 | Build tests                               |
| `tests/ci/test_ci_data_patch.py`                                   | The path `data/source/iana-root.html` | Scratch-repo patch tests                  |
| `.github/workflows/update-data.yaml`                               | Eight `download-tld-pages` steps      | Nightly page refresh                      |

## Field transformations

The mappings in the evidence table are not all direct. Each needs a test.

- `tld_iso` is `iso3166_code` lowercased. `_add_idn_mappings()` looks up lowercase keys, so an
  uppercase value silently drops the `idn` array from all 61 ccTLDs.
- Nameserver `name` becomes `hostname` before `_enrich_nameservers_with_asn()`.
- `tld_updated` is `[last_updated]`, and is omitted when `last_updated` is null.
- `rdap_server` is `rdap_base_urls[0]`, then the RDAP bootstrap file, then the supplemental file.
  19 records have no JSON URL and rely on the fallback today.
- More than one distinct URL in `rdap_base_urls` fails the build. The schema allows it and no record
  has it, so the output model is extended deliberately when it first appears.
- `language_name_en` follows the final `language_code`. `LANGUAGE_NAMES_EN` gains every code IANA
  uses that it lacks, including `ory`, `yi`, `sat` and `ks`.
- The derived `type` for `iana_tag: "test"` stays `gtld`, as today.
- Change detection ignores `meta.generated` from the start, as the RDAP validator ignores its
  timestamp.

## Review outcome

Reviewed 2026-11-10 by codex 0.167.0 and agy 1.5.5 (on its fallback model, `gemini-3.8-flash`) at
`high` effort. Both said the direction is sound and the plan was not ready as written. Accepted
findings are folded into the tables above and the phases below.

Ruled by Eric on 2026-11-10:

- **Decision 9.** `emerson` and `xn--4gq48lf9j` leave both `tlds.json` and `agreements.json`,
  because `agreements.json` is built from the TLD records. Documented as breaking.
- **Download failure policy.** A download is parsed before it replaces the stored file. A fetch
  failure continues on the previous file and alerts. An invalid payload fails the job.
- **Schema validation.** The fail-closed parser guards the runtime path with no new dependency. A
  test validates the stored JSON against the stored schema with `jsonschema`, added to the `dev`
  group. The parser tolerates unknown keys, as the schema's `specversion` note requires.
- **Decision 7.** `type` is `gtld | cctld | special-use`. `.arpa` and the 8 reserved names are
  `special-use`; `test` stays `gtld`.
- **Decisions 14 to 16.** Live files carry no date prefix; fixtures do. This settles agy's dissent
  on the live file name. The old HTML is kept, against agy's advice to delete it.

- **selectolax 1.0** stays in this branch as its final code phase, against codex's advice to split
  it. After this plan only `src/parse/registry_agreement_page.py` uses selectolax.

## Status

Implemented on 2026-11-10 and 2026-11-11 on branch `iana-tlds-json`. Uncommitted, pending Eric's
final review.

- **Pass 1 (Phases 0 to 2):** done. Reviewed by codex and agy at `high` effort for three rounds.
  The loop was capped with one finding open, which Eric then ruled on: the dev group uses
  `jsonschema[format-nongpl]`, and the runtime parser checks ports and hostname lengths.
- **Pass 2 (Phases 3 to 5):** done. Reviewed for three rounds at `high` effort. agy returned a
  review in round 1 only and timed out in rounds 2 and 3, so those two are codex alone. The fixes
  for round 3's three findings were applied at Eric's direction and are not reviewed.

Departures from the plan as written:

- `sources.iana_root_db` in the generated files became `sources.iana_tlds`. Eric confirmed.
- `sony` and `icann-ebero` needed no triage. Both still resolve; the zero-TLD reading came from
  the broken HTML.
- `selectolax` is pinned to 1.0.2, the current patch release, not 1.0.0.
- The parser also enforces the schema's cross-field rules, added in review.
- Phase 5 gained a README stability note: the data has no versioned releases yet.
- The download failure policy changed on 2026-11-11. A rejected payload no longer fails the job;
  it continues on the stored file and alerts, like a failed fetch.
- `jsonschema` became a runtime dependency on 2026-11-11, reversing the "no new dependency"
  ruling. The downloader validates each fetched TLD JSON against IANA's schema.

Durable decisions are in
[the memory log](../../memory/log/2026-11-10-iana-tlds-json.md).

## Open questions

- **Regeneration cadence.** Whether IANA rewrites `meta.generated` when nothing else changed is not
  yet observed. Change detection ignores the field either way.
- **`tests/fixtures/source/2025-11-18-tlds/` and the dated `root*.html` fixtures** have no test
  reading them now. They are kept as frozen history per decision 15.

## Phase 0: Lookup helper and fixture

Additive only. The HTML pipeline keeps working.

- [x] Test helper that resolves a fixture slug to its latest dated file: exact slug match, parsed
      dates, error on no match
- [x] Tests for no match, several dates, and a near-miss slug
- [x] `src/config.py` gains the `iana-tlds.json` and `iana-tlds-schema.json` source entries
- [x] Trimmed fixture `tests/fixtures/source/core/2026-11-10-iana-tlds.json` covering each status,
      each type, an IDN ccTLD, an IDN gTLD, `.arpa`, and a record with null manager

## Phase 1: JSON parser

Additive only.

- [x] `src/parse/` module that reads the file with `json` and returns typed records
- [x] Fail closed on unknown `status`, `type` or `specversion`, a missing required key, or a wrong
      type; ignore unknown keys
- [x] `jsonschema` in the `dev` group, vetted first; a test validates the stored JSON against the
      stored schema
- [x] Content-changed validator that ignores `meta.generated`
- [x] Tests: happy path, empty `domains`, each null-able field null, unknown enum value, duplicate name

## Phase 2: Switch the build, consumers and generated data together

One step, because the reconciliation tests compare the build against committed `data/generated/`.

- [x] `src/build/tlds.py` reads the JSON records; apply every item under "Field transformations"
- [x] `delegated`, `iana_tag`, `type` per decisions 2, 3 and 7
- [x] Archive seed file, its loader and validation; `archived.iana_tag` and `tld_created` output
- [x] Reserved rows flow through with no orgs, nameservers or dates
- [x] `language_code` precedence, `language_code_source`, and the matching `language_name_en`
- [x] New fields per the proposed-names table
- [x] Script agreement test with the 23-entry name-to-code table
- [x] Move every reader in the consumer table to the JSON records, including
      `generate_idn_script_mapping.py` and the provenance string in `src/build/organizations.py`
- [x] Prune per-TLD files with no record, after all writes succeed; test set equality, not a count
- [x] Rebuild `data/generated/` and review the diff against the evidence table
- [x] Update count baselines in `tests/integration/test_build_reconciliation.py`
- [x] Triage drift that built up since 2026-09-28: `bh` and `sc` in both IANA and supplemental RDAP;
      `sony` and `icann-ebero` mapping to zero TLDs; organization name changes
- [x] `test_every_idn_has_an_english_meaning` accepts IANA's translation as a source

## Phase 3: Download and nightly

- [x] Download the JSON and schema with conditional requests, to a temporary file; parse, then
      replace the stored file
- [x] Fetch failure continues and alerts; an invalid payload fails the job
- [x] Remove the per-TLD page download, its CLI flag and `make download-tld-pages`
- [x] Remove the eight `download-tld-pages` steps from `.github/workflows/update-data.yaml`, and
      update `check-asn-drift.yaml` and the metadata keys
- [x] Confirm the `bin/ci-*` patch scripts accept the new paths under `data/source/`

## Phase 4: Remove the HTML pipeline, archive its files, selectolax 1.0

- [x] Delete `src/parse/root_db_html.py`, `src/parse/tld_html.py`, `src/analyze/root_db_html.py` and
      their tests; drop the `ROOT_ZONE_DB` entries from `src/config.py`
- [x] Move and rename the old HTML files and fixtures per the table above
- [x] Move `src/parse/registry_agreement_page.py` to `selectolax.lexbor.LexborHTMLParser`
- [x] Rewrite `scripts/analyze_nameserver_ips.py` to read the JSON, which removes its selectolax use
- [x] Bump `selectolax` to 1.0.0 in `pyproject.toml` and `uv.lock`; this supersedes PR #139

## Phase 5: Documentation

- [x] README schema block and the "`delegated: false` records" section
- [x] Memory log entry for the decisions above, and the memory index line
- [x] Move this plan to `docs/plans/archive/`
