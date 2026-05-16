---
title: Atomic JSON writes
summary: write_json_if_changed now writes via NamedTemporaryFile + fsync + chmod 0o644 + os.replace, so mid-write failures can't leave torn or truncated files on disk
created: 2026-05-15
author: Eric Case
tags: [log, decision, io, safety]
---

# 2026-05-15 - Atomic JSON writes

`_atomic_write_json` in `src/utilities/content_changed.py`:

1. Write JSON to `NamedTemporaryFile` in the target's parent dir
2. `flush()` + `fsync(fileno)` so bytes hit disk
3. `chmod` to `0o644`
4. `os.replace(tmp, target)` (atomic on POSIX and Windows when source and target are on the same filesystem)
5. `finally`: unlink the temp file if it still exists (rename succeeded → already gone; rename failed → cleanup)

## Why each piece

- **Same-dir temp**: keeps the rename on one filesystem so `os.replace` is atomic.
- **fsync before rename**: `os.replace` gives visibility-atomicity, not durability. Without fsync, a outage between rename and the next sync can lose the bytes even though the rename "succeeded".
- **Explicit 0o644**: `NamedTemporaryFile` creates with `0o600` by design. These files are served by CDNs and read by other processes; `0o600` would silently break propagation. The `chmod` restores the umask-default that the old direct-open path produced.
- **Atomic vs. naive write**: the previous code opened the target directly with `"w"`. A crash mid-write left the consumer-facing file truncated. Now it's untouched until the rename.

## Guarantees verified by tests

- `test_atomic_write_uses_0o644_permissions`
- `test_atomic_write_preserves_original_when_update_fails` (file byte-identical after rename failure)
- `test_atomic_write_leaves_no_temp_file_on_success`
