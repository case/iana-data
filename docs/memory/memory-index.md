# iana-data memory

Project decisions, architecture, and conventions. Two core files plus a dated `log/` subdir.

Agents: consult before suggesting layout, naming, dependencies, vendors, or conventions. Verify against the codebase before relying on a specific path or name - memory can lag reality.

## Core
- [Product](product.md) - what iana-data is and why; implementation-independent
- [Architecture](architecture.md) - current implementation: stack, layout, conventions

## Log (newest first)
- [2026-05-16 Per-field source-of-truth](log/2026-05-16-per-field-truth.md) - each IANA source authoritative for a specific field set; reconciliation tests encode the rule
- [2026-05-15 Per-TLD JSON publication](log/2026-05-15-per-tld-publish.md) - per-TLD files + slim index alongside bulk tlds.json
- [2026-05-15 Atomic JSON writes](log/2026-05-15-atomic-writes.md) - NamedTemporaryFile + fsync + chmod 0o644 + os.replace pattern
- [2026-05-15 bin/ scripts replace make targets](log/2026-05-15-bin-scripts.md) - bin/setup, bin/lint, bin/test; make retains domain targets
- [2026-05-15 Switch from npm to pnpm](log/2026-05-15-pnpm.md) - pnpm-lock.yaml replaces package-lock.json
- [2026-05-15 Bootstrap memory system](log/2026-05-15-bootstrap.md) - initial setup of this memory system
