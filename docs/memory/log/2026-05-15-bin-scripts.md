---
title: bin/ scripts replace make targets for developer workflow
summary: bin/ scripts replace every make target; dev-loop scripts plus bin/<verb> --<option> for domain operations, and CI calls them directly
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

## Domain operations

On 2026-11-20 the remaining targets moved to `bin/` and the Makefile was deleted. Related operations
share one script, chosen by an option: `bin/download --iana|--iptoasn`, `bin/analyze
--data|--idn-scripts|--registry-agreements|--tlds-json`, `bin/generate --idn-mapping`, and `bin/checkly
--test|--preview-deploy|--deploy|--info`. Each prints its options with `--help` and rejects an unknown
option or a second argument with exit 2. `make typecheck` and `make check-circular-imports` have
no script: `bin/lint` runs pyright and `bin/test` runs `tests/test_circular_imports.py`.

## Why

`bin/*` is the cross-project convention in the user's other repos. Standard semantics: scripts forward `"$@"` where it makes sense (lint takes optional paths, test takes pytest args), exit on first error via `set -euo pipefail`, and live at a predictable path that's easy to teach to a new contributor.

## Tests guarding the migration

`tests/test_production_smoke.py` checks that every `bin/` script is executable, that each
`bin/analyze` report runs, and that each option script refuses a second argument.
