---
title: bin/build requires an explicit mode
summary: bare bin/build prints help; --preserve-asn (local, keep committed ASN) vs --all (full, refresh ASN from iptoasn, used by CI); stops a plain build silently churning ASN from a stale local snapshot
created: 2026-05-30
author: Eric Case
tags: [bin-scripts, build, iptoasn, asn, ci]
---

# bin/build requires an explicit mode (2026-05-30)

`bin/build` used to build unconditionally and read the local `data/source/iptoasn` snapshot, so any unrelated local build (e.g. refreshing places data) recomputed every nameserver IP's ASN and churned `asn`/`as_org` across ~290 per-TLD files plus `tlds.json` and `organizations.json`. The `--preserve-asn` flag (added in `40973e16`) avoided this, but it was opt-in, so the default `bin/build` kept re-introducing the churn.

The change makes the mode mandatory:

- **`bin/build`** (no args) and `-h`/`--help` print usage and exit 0; they build nothing. A bare invocation can no longer silently refresh ASN.
- **`bin/build --preserve-asn`** — build, keeping the ASN already in the committed `tlds.json` (`_asn_lookup_from_committed`, reads the on-disk file, so restore a flapped `tlds.json` *before* relying on it). Local/dev default.
- **`bin/build --all`** — full build, refreshing ASN from the local iptoasn file. The data-update workflow (`.github/workflows/update-data.yaml`) uses this; it is the only place ASN is meant to move.
- Unknown option → usage on stderr + exit 2.

Also updated the Makefile help and the `README.md` "delete it and rebuilds it" line to `--preserve-asn`. Note: the script no longer forwards extra args to `src.cli` (it maps each mode to a fixed arg list).
