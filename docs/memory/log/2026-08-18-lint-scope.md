---
title: bin/lint defaults to the whole repo so every runner agrees on scope
summary: bin/lint hardcoded `paths=(src/ tests/)`, so scripts/ and bin/ were never linted by the project while the global pre-commit hook ran `ruff check .` and saw 21 findings there. Scope now defaults to `.`; ruff.toml stays the only place policy lives.
created: 2026-08-18
author: Eric Case
tags: [log, decision, lint, ruff, pyright, tooling]
---

# 2026-08-18 - Lint scope is whole-repo

A routine commit failed the global lefthook `ruff-check` job with 21 errors in `scripts/` and `bin/lint-json.py`. None were new: `git diff ad16e765 HEAD -- scripts/ bin/lint-json.py ruff.toml bin/lint` is empty, and those files were last touched in May and June.

The cause was scope, not drift. Two runners disagreed about which files to read:

| Runner | Command | Files |
|---|---|---|
| `bin/lint`, and CI via `bin/test` | `ruff check src/ tests/` | 2 directories |
| global lefthook hook | `ruff check .` | whole repo |

`ruff.toml` declares which *rules* apply but says nothing about which *files*, so the real scope decision lived in a bash array inside `bin/lint` where no other tool could see it. The 2026-08-07 ruff 0.16 pass looked complete because it was verified with `bin/lint`, which is structurally incapable of failing on `scripts/`. Its "72 violations" census was scope-limited for the same reason.

## Decision

`bin/lint` defaults to `paths=(.)`. Explicit path arguments still work for targeted runs. Nothing was added to `ruff.toml`: whole-repo discovery is already ruff's default, so the runners now agree because nothing narrows the scope, not because two places are kept in sync by hand. This widens `ruff check`, `ruff format --check` and `pyright` together, since all three read the same array.

`ruff format --check .` was already clean. The 21 ruff findings and 2 pyright findings were fixed in the same pass.

## Notable fixes

- **`EXE001` x10**: shebangs removed rather than adding the executable bit. Every caller uses `uv run python scripts/...` (Makefile, `bin/build`, `bin/fetch-coordinates`, `update-data.yaml`), no script carries PEP 723 metadata, and `#!/usr/bin/env python3` would run system Python without the project venv against files that import `src.*`. Making them executable would have created a broken entry point. Matches the `src/cli.py` call in [2026-08-07 ruff-defaults](2026-08-07-ruff-defaults.md).
- **`RUF100` x5**: `# noqa: E402` removed because E402 is not in the current rule set. If a future explicit `select` enables `E4`, these come back: all five sit under a `sys.path.insert` and would violate again.
- **`S110`**: `except Exception: pass` around IPv6 parsing narrowed to `ValueError`, with a skip counter printed at the end. The file has no logger and is print-driven, so a count line matches its idiom.
- **`DTZ007`**: suppressed with a reason. The registry CSV carries date-only values and the parsed result feeds year counts and display only. `.date()` does not silence the rule (verified), and `.replace(tzinfo=UTC)` would fabricate precision the source lacks.
- **pyright `reportPossiblyUnbound` x2**: the `HAS_PYCOUNTRY` boolean could not be tied to the `pycountry` binding. Replaced with a `pycountry = None` sentinel and an `is None` test, which pyright narrows without a `type: ignore`.

## Still open

`ruff.toml` has no `select`, so the repo rides ruff's implicit defaults (412 rules here, after the `BLE001` ignore). The 2026-08-07 entry says the file makes the rule set "an explicit, reviewable choice"; it does not, and the next ruff minor can move it again with no diff. Pinning `select` is deferred to its own change so that findings from a rule-set change are not confused with findings from this scope change.
