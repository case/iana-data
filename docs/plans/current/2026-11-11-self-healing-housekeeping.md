# Self-healing housekeeping drift

## Problem

Ordinary upstream change fails the nightly, and the nightly then stops updating every source. The
nightly failed from 2026-09-29 to 2026-11-11 for this reason.

Three integrity tests fail on routine upstream change:

- `tests/integration/test_iana_tlds_integrity.py::test_supplemental_rdap_does_not_overlap_with_iana_tlds_json`
  fails when IANA starts publishing an RDAP URL for a ccTLD in `data/manual/supplemental-cctld-rdap.json`.
- A new IANA language code with no entry in `LANGUAGE_NAMES_EN` (`src/build/idn_language.py`) fails
  the build.
- `tests/integration/test_organizations_integrity.py::test_source_names_appear_in_raw_data` fails
  on an IANA org name change. The fix is to move the stale name to `archived.iana` in
  `data/manual/organizations.json`.

Warnings have the opposite problem. Nobody reads a pytest warnings summary in a nightly run.

## Rule

No tolerated warning without an alert or a bot PR. A condition is either a hard failure, or it
warns in the nightly and something reaches a human. A warning that only prints is not allowed.

## Approach

Reuse the ASN drift machinery: `check-asn-drift.yaml`, `bin/ci-archive-asn-labels` and
`bin/ci-open-drift-pr`. Each housekeeping failure becomes a nightly warning, and a bot opens the
fix PR.

## Phase 0: inventory

- [ ] List every warning the suite can emit, with its alert path. Current set:
  - `AsnDriftWarning`, from `tests/integration/asn_drift.py`. Covered by `check-asn-drift.yaml`.
  - TLD list drift, from `tests/integration/test_source_drift.py`. No alert today.
- [ ] Decide, per warning, whether it becomes a failure or gets an alert path.

## Phase 1: housekeeping drift PRs

- [ ] Supplemental RDAP overlap: propose removing the overlapping entry.
- [ ] New IANA language code: propose a `LANGUAGE_NAMES_EN` entry.
- [ ] IANA org name change: propose moving the stale name to `archived.iana`.

## Phase 2: ASN drift successors

- [ ] When an asn label drifts, propose its successor spelling too, matched by ASN number and
      kept only when a full build shows it on a TLD nameserver address. See
      [2026-11-11 iptoasn labels](../../memory/log/2026-11-11-iptoasn-labels.md).

## Phase 3: TLD list drift

- [ ] Give the `tlds.txt` versus IANA TLD JSON drift an alert path, or make it a failure.
