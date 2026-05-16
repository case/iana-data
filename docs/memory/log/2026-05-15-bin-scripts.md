---
title: bin/ scripts replace make targets for developer workflow
summary: bin/setup, bin/lint, bin/test replace make deps/lint/test/coverage; CI calls them directly
created: 2026-05-15
author: Eric Case
tags: [log, decision, conventions, tooling]
---

# 2026-05-15 - bin/ scripts replace make targets for developer workflow

## Change

Three new bash scripts at `bin/`:

- `bin/setup` — `uv sync && pnpm install`
- `bin/lint` — `ruff check`, `ruff format --check`, `pyright` (runs all three even if an earlier one fails, so devs see the full set of findings in one pass)
- `bin/test` — `bin/lint` then `uv run pytest --cov=src --cov-report=term-missing`

Deleted Make targets: `deps`, `lint`, `test`, `coverage`. CI workflows (`tests.yaml`, `update-data.yaml`) updated to call `bin/setup` and `bin/test` instead of `make deps` / `make test`.

## What's still in the Makefile

Project-specific orchestration: `make build`, `make download-core`, `make download-tld-pages`, `make analyze`, `make generate-idn-mapping`, `make typecheck`, `make checkly-*`. These are domain operations, not dev-loop commands.

`make help` lists both, with the bin/* group under a `Scripts (run directly, not via make):` heading so contributors don't try `make bin/lint`.

## Why

`bin/*` is the cross-project convention in the user's other repos. Standard semantics: scripts forward `"$@"` where it makes sense (lint takes optional paths, test takes pytest args), exit on first error via `set -euo pipefail`, and live at a predictable path that's easy to teach to a new contributor.

## Tests guarding the migration

- `test_bin_scripts_are_executable` — confirms `bin/setup`, `bin/lint`, `bin/test` exist and are executable
- `test_makefile_targets_exist` — re-anchored to do per-line matching (previous substring check was passing `target="test"` only because `checkly-test:` matched as a substring)
