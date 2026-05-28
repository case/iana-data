#!/usr/bin/env python3
"""Validate that every JSON file in the repo parses cleanly."""

import json
import sys
from pathlib import Path

EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__"}

# Test fixtures that are intentionally invalid JSON.
EXCLUDED_FILES = {
    Path("tests/fixtures/metadata/corrupted-metadata.json"),
}


def find_json_files(root: Path):
    for path in root.rglob("*.json"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.relative_to(root) in EXCLUDED_FILES:
            continue
        yield path


def main() -> int:
    root = Path.cwd()
    bad: list[tuple[Path, str]] = []
    count = 0
    for path in find_json_files(root):
        count += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            bad.append((path.relative_to(root), str(e)))

    if bad:
        for rel, err in bad:
            print(f"{rel}: {err}", file=sys.stderr)
        print(f"\n{len(bad)} of {count} JSON file(s) failed to parse.", file=sys.stderr)
        return 1

    print(f"{count} JSON file(s) parse cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
