---
title: write_json_if_changed switched to byte-equality
summary: dict equality is order-insensitive; serialized-JSON equality catches field-order changes; regression test pinned
created: 2026-05-25
author: Eric Case
tags: [build, writer, json, regression-test]
---

# Writer byte-equality (2026-05-25)

`src/utilities/content_changed.py:write_json_if_changed` previously compared new vs. existing data via `new_dict == existing_dict`. Python dict equality is **order-insensitive**, so any pure field-reorder change in the build silently no-op'd the writer: the on-disk JSON kept the old field order forever.

This bit us when reordering `nameservers` to be the last field in each TLD record. The change was correct in code but never propagated to disk. The fix:

- Compare via `json.dumps(...)` strings instead of dict equality. Same serialization parameters as the actual write (`indent`, `ensure_ascii=False`) so the comparison reflects exactly what would land on disk.
- Helper `_canonical_json` shared between the change check and the write path.
- Regression test `tests/utilities/test_content_changed.py::test_write_json_if_changed_detects_key_reorder` writes `{"a": 1, "b": 2}` then re-writes with `{"b": 2, "a": 1}`; asserts the file is rewritten with the new key order.

**Implication for the build:** field-order in `_build_tld_entry` (and equivalent functions for sibling artifacts) is now the source of truth for JSON output order. Insertion order of `entry[...]` assignments determines the serialized field order.
