---
title: IANA TLD JSON is the canonical TLD source
summary: IANA redesigned the Root Zone Database pages and broke both HTML parsers; the nightly failed from 2026-09-29. The build now reads IANA's JSON export, the HTML pipeline is gone, and values IANA dropped live in an archive seed.
created: 2026-11-10
author: Eric Case
tags: [log, decision, sources, iana, schema, download, archive]
---

# 2026-11-10 - IANA TLD JSON as the canonical source

Plan: [2026-11-10-iana-tlds-json](../../plans/archive/2026-11-10-iana-tlds-json.md), which holds the
field-by-field evidence.

## Source

`data/source/iana-tlds.json` (`https://data.iana.org/TLD/v1/tlds.json`) is the only IANA TLD source.
The index parser, the per-TLD page parser and the page downloader are deleted. The last HTML copies
are frozen under `data/source/archive/`, with their first-capture dates as prefixes.

The parser (`src/parse/iana_tlds_json.py`) is hand-written and fails closed. It rejects an unknown
`status`, `type` or `specversion`, a missing key the build reads, a wrong type, and a broken
cross-field rule of IANA's schema. It ignores unknown keys, as the schema's `specversion` note
requires. The name is checked as an LDH label because it becomes a file name.

`jsonschema` is a runtime dependency, with its `format-nongpl` extra, because jsonschema silently
skips a format whose optional package is absent. The downloader validates each fetched TLD JSON
against the stored schema before it is stored (`src/parse/iana_tlds_schema.py`), and a test
validates the stored pair.

Rejected alternative: the hand parser as the only runtime guard, with `jsonschema` dev-only. A
hand-written check cannot track IANA's schema. Each gap is a value the parser accepts and the
schema forbids, which is stored and then fails the schema test. Hand-registered format checkers
have the same flaw.

## Download policy

A download is parsed before it replaces the stored file, and the replace is atomic.

- A failed fetch is `error`. CLI exit 3.
- A rejected payload is `invalid`. CLI exit 4.

Neither is 1 or 2, because an uncaught exception exits 1 and argparse exits 2.

Both keep the stored file, so the nightly continues on yesterday's copy and alerts. Only a crash
of the downloader fails the job.

Rejected alternative: failing the job on a rejected payload. That costs every other source its
update that night, and the stored file is safe to build from.

The schema file is checked too: it must be a valid JSON Schema, carry IANA's `$id`, and reject a
record with no fields. An empty object is a valid schema that accepts everything. The schema is
fetched first. If the TLD JSON left in place afterwards does not conform to a newly fetched
schema, the old schema is restored, so the stored pair always agrees.

The workflow calls the CLI directly, not `make`, which turns every failure into exit 2. Change
detection ignores `meta.generated`.

## Data model

- `delegated` is `status == "active"`. `status` is published too.
- `iana_tag` takes IANA's four current values. `type` is `gtld | cctld | special-use`; `test`
  derives `gtld`.
- The 18 dropped `iana_tag` values are kept per TLD at `archived.iana_tag`, shaped
  `{"value", "archived_on"}`, like the organizations `archived` bucket.
- `tld_created` has no live source. It comes from `data/manual/tld-archive.json`, extracted once
  from commit `644440d3`. A test pins the seed's size, so a deleted entry fails.
- The 8 reserved special-use names are records, with `delegated: false`.
- `emerson` and `xn--4gq48lf9j` left IANA's data, so they left every artifact.
- `language_code` is IANA's unless ours extends it with a subtag. `language_code_source` is
  `IANA`, `refined` or `derived`.
- More than one distinct URL in `rdap_base_urls` fails the build. The output model holds one
  server, and is to be extended deliberately when a second first appears.
- `sources.iana_root_db` became `sources.iana_tlds`.
- Per-TLD files with no record are pruned, after every write succeeded.

## File naming

Live source files carry no date prefix and are overwritten in place. Test fixtures are named
`yyyy-mm-dd-{slug}` by capture date, and `tests/dated_fixtures.py` resolves the latest for a slug.
A changed upstream format gets a new dated fixture and the old one stays.

## Stability

The data has no versioned releases or changelog. The README now says so.
