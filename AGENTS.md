# iana-data

A compilation of IANA- and ICANN-published, canonical data about the domain ecosystem. See [`docs/memory/product.md`](docs/memory/product.md) for what this is, [`docs/memory/architecture.md`](docs/memory/architecture.md) for how it's currently built.

<!-- project-memory:start -->

## Project memory

Project memory lives in `docs/memory/`. The index is at [`docs/memory/memory-index.md`](docs/memory/memory-index.md).

**Before suggesting** file layout, naming, dependencies, vendor choices, or conventions: read the index, then read the matching entry. The codebase is the source of truth - verify against it before relying on a specific path or name in memory.

**When a new decision is made**: write or update the relevant memory entry in the same conversation, and surface the diff. Memory updates review like any other code change. **Exception**: if the entry changes how the memory system itself works (conventions, schema, naming, structure), draft the body inline in chat first and wait for explicit go-ahead before writing.

**Entries are concise**: bigger than a commit message, smaller than a design doc. Short rationales per decision.

**Log filenames**: use a 1-3 word slug after the date. Topic distillation, not a sentence.

**When memory contradicts the code**: surface the conflict. Trust the code after verifying, then update or remove the stale entry.

**Plans**: plan documents live in `docs/plans/current/`. Move a plan to `docs/plans/archive/` when its work is done, so `current/` lists only open work. Any relative links to a "current" plan will need to be updated to include its `archive/` path.

**Monorepos**: if this repo contains subprojects with their own `docs/memory/`, treat each subproject's memory as authoritative for work inside that subproject. The root `docs/memory/` covers concerns that span subprojects. See [the project-memory README](https://github.com/case/project-memory#monorepos) for the rationale.

<!-- project-memory:end -->
