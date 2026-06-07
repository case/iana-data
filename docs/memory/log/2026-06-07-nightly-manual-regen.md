---
title: Nightly rebuild now picks up manual curation, not just IANA source changes
summary: update-data.yaml always rebuilds (--all when IANA source changed, else --preserve-asn) so data/manual/ edits propagate to data/generated/ on the nightly schedule without ASN churn. Previously the build was gated on data/source/ changes only, so manual curation never regenerated until a coincidental IANA change.
created: 2026-06-07
author: Eric Case
tags: [log, decision, ci, build, organizations]
---

# 2026-06-07 - Nightly rebuild picks up manual curation

## Problem

`update-data.yaml` gated the build on `git diff --quiet data/source/` and only ran `bin/build --all` when downloaded IANA source files changed. `data/manual/` (editorial curation: organizations, aliases, coordinates) is not checked and does not change during a nightly run, so manual edits sat in source but never regenerated into `data/generated/` until an unrelated IANA-source change happened to trigger a build. The org-mapping work accumulated ~2 weeks of un-regenerated curation this way.

## Change

The nightly now **always rebuilds**, choosing the mode:

- IANA source changed (`source_changed == 'true'`) -> `bin/build --all` (full refresh incl. ASN from the iptoasn artifact, as before).
- otherwise -> `bin/build --preserve-asn` (regenerate annotations from `data/manual/` + committed source, keeping ASN from the committed `tlds.json`).

Tests also always run now (they were gated on `source_changed` too), so a manual-driven regen is tested before commit. The commit message distinguishes the cases: "Update IANA source data files" vs "Regenerate data from manual curation".

## Why --preserve-asn for the no-source case

iptoasn updates daily and is noisy (IP->ASN assignments flip between snapshots). Refreshing ASN every night (`--all`) would churn `data/generated/` daily, the exact thing `--preserve-asn` exists to prevent (see [2026-05-30 build modes](2026-05-30-build-modes.md)). Keeping ASN frozen except on IANA-source changes preserves that property while still flushing manual curation.

## No-op safety

A nightly with no real change produces no commit: the writer compares content with `exclude_fields=["publication"]` (`src/utilities/content_changed.py`), so an unchanged rebuild yields zero file diffs. Loop-safe too: the bot pushes with the default `GITHUB_TOKEN` (no workflow re-trigger) and a regen only touches `data/generated/`.

## Operational note

Keep the local iptoasn file fresh (`make download-iptoasn`) before adding/verifying org mappings. `tests.yaml` builds from the daily `update-iptoasn` artifact (current), so a stale local iptoasn can pass locally while CI fails on a string that only exists in the old snapshot.
