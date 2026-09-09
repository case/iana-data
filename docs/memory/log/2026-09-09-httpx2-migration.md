---
title: Migrate from httpx to httpx2
summary: httpx2 is a same-API fork of httpx 0.28.1; the migration is a rename, and the only behavior change that reaches us is SSL trust anchoring
created: 2026-09-09
author: Eric Case
tags: [dependencies, http, ssl, supply-chain]
---

# Migrate from httpx to httpx2 (2026-09-09)

`httpx2` ([pydantic/httpx2](https://github.com/pydantic/httpx2)) is a fork of `httpx` 0.28.1 published by Pydantic. Its [migration guide](https://github.com/pydantic/httpx2/blob/main/docs/migration.md) states the public API is unchanged: same `Client`, `Response`, `MockTransport`, and exception hierarchy. We were pinned at `httpx>=0.28.1`, the exact fork point, so there is no behavior delta in our call surface and no test needed rewriting to match new semantics.

`iana-data` was the only requirer of `httpx` in the lock, so this is a clean swap rather than an incremental migration. No `alias_httpx()` bridge, no side-by-side period.

## What changed

`import httpx` became `import httpx2` in `src/utilities/retry.py`, `src/utilities/download.py`, `scripts/fetch_place_coordinates.py`, and four test modules. `pyproject.toml` moved to `httpx2>=2.12.0`.

The renames that a plain import swap does **not** reach were the real work: roughly 45 `unittest.mock.patch("httpx.Client")` targets in `tests/utilities/test_download.py` and `tests/utilities/test_tld_download.py`, plus one `patch("src.utilities.download.httpx.Client")`. These are strings, so no type checker or linter sees them. They fail loudly rather than silently only because `httpx` is fully uninstalled - `mock.patch` raises `ModuleNotFoundError` on an unresolvable target. Had `httpx` stayed in the environment as a transitive dependency, a missed target would have patched the wrong module's `Client` while the test still passed against its mock.

## SSL trust anchoring is the one real behavior change

`httpx2` verifies TLS against the operating system trust store via [`truststore`](https://truststore.readthedocs.io/), where `httpx` used `certifi`'s bundled CA set. `SSL_CERT_FILE` and `SSL_CERT_DIR` are still honored first, and explicit `verify=` still works. We pass neither, so every IANA, ICANN, Wikidata, and iptoasn fetch now anchors on the host's CA store.

This is untested here by construction: every test in the suite drives `MockTransport` or a `Mock(spec=Response)`, so nothing exercises a real TLS handshake. The exposure is that a CI runner or container with a thin CA store could fail a fetch that `certifi` would have accepted. Nightly runs on `ubuntu-24.04` and `ubuntu-slim` both ship `ca-certificates`, so this is a watch item, not a known defect.

## Not adopted

`httpx2` bundles SSE (`client.sse()`) and WebSockets. We use neither, and neither `httpx-sse` nor `httpx-ws` was a dependency to drop.

## Dependency effect

`certifi` and `httpcore` leave; `truststore` and `httpcore2` arrive. Net count is roughly flat. The trust anchor moves from a bundled, dependency-pinned CA set to one the operating system maintains - which is the better default for a nightly job on a managed runner, since CA rotation stops being gated on a dependency bump.
