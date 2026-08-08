---
title: Adopt ruff's default rule set via ruff.toml
summary: ruff 0.16 expanded its implicit defaults from 59 rules to 413; ruff.toml now records the rule set explicitly
created: 2026-08-07
author: Eric Case
tags: [lint, ruff, ci, conventions]
---

# Adopt ruff's default rule set via ruff.toml (2026-08-07)

The repo had no `[tool.ruff]` section anywhere, so lint policy was whatever ruff's implicit defaults happened to be. Ruff [0.16.0](https://astral.sh/blog/ruff-v0.16.0) expanded those defaults from 59 rules (`E4`, `E7`, `E9`, `F`) to 413, and the Dependabot bump surfaced 72 violations.

The decision is to **adopt the new defaults** rather than pin back to the old set. `ruff.toml` now exists to make the rule set an explicit, reviewable choice.

Deviations recorded in `ruff.toml`:

- **`BLE001` ignored repo-wide.** Twelve sites in `download.py`, `content_changed.py`, `tlds.py`, and `parse/root_db_html.py` catch `Exception` at an I/O or parse boundary, log it, and degrade to a defined fallback (`"error"`, treat-as-changed, omit optional field). That is the pipeline's deliberate resilience convention: one malformed source file must not abort a run. Narrowing all twelve would mean enumerating exception types for `json.load`, `.decode("idna")`, and httpx, where guessing wrong turns a logged degradation into a crash. A thirteenth site was flagged by both `BLE001` and `S110` and is fixed below rather than ignored.

Nothing else is ignored. The remaining 59 violations were fixed, notably:

- **`S110` in `build/tlds.py`** was the one genuine outlier: a silent, unlogged `except Exception: pass` around the IDN punycode decode, three lines from twelve siblings that all log. Narrowed to `except UnicodeError` (covers both `UnicodeDecodeError` from bad punycode and `UnicodeEncodeError` from non-ASCII input) and given a `logger.warning`.
- **`EXE001` in `src/cli.py`**: the `#!/usr/bin/env python3` shebang was vestigial. Every caller uses `python -m src.cli` (Makefile, `bin/build`), so the shebang was removed rather than the file made executable.
- **`PLW1510`** (7 sites): tests that deliberately assert on `returncode` now pass `check=False` explicitly.
- **`TRY002`** (6 sites in `tests/utilities/test_download.py`): mock guards for unexpected URLs became `AssertionError`; simulated transport failures became `RuntimeError`. Both still exercise the same `except Exception` production paths.

`target-version` is not set in `ruff.toml`. Ruff still infers 3.13 from `requires-python` in `pyproject.toml` even when config resolves from a standalone `ruff.toml` (verified with `ruff check --show-settings`). This matters because `UP017` (`datetime.UTC`) is 3.11+ only; a mis-inferred target would silently drop 15 of the findings.
