#!/usr/bin/env python3
"""Validate JSON: every file parses, and data artifacts are canonical.

Syntax-checks every committed JSON file; format-checks data/generated and
data/manual against the writer's canonical form. ``--fix`` rewrites offenders.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utilities.content_changed import (  # noqa: E402
    canonicalize_json_file,
    is_json_canonical,
)

EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__"}

# Test fixtures that are intentionally invalid JSON.
EXCLUDED_FILES = {
    Path("tests/fixtures/metadata/corrupted-metadata.json"),
}

# Dirs whose JSON we author/generate, so we format-enforce them. data/source
# holds verbatim upstream captures: parsed, but never reformatted.
FORMAT_DIRS = (Path("data/generated"), Path("data/manual"))


def find_json_files(root: Path):
    for path in root.rglob("*.json"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.relative_to(root) in EXCLUDED_FILES:
            continue
        yield path


def in_format_scope(rel: Path) -> bool:
    return any(d == rel or d in rel.parents for d in FORMAT_DIRS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="rewrite non-canonical data JSON files in place",
    )
    args = parser.parse_args()

    root = Path.cwd()
    parse_errors: list[tuple[Path, str]] = []
    offenders: list[Path] = []
    fixed: list[Path] = []
    count = 0

    for path in find_json_files(root):
        count += 1
        rel = path.relative_to(root)
        in_scope = in_format_scope(rel)
        try:
            text = path.read_text(encoding="utf-8")
            if in_scope and not args.fix:
                # is_json_canonical parses, so it doubles as the syntax check.
                if not is_json_canonical(text):
                    offenders.append(rel)
            else:
                json.loads(text)
        except (json.JSONDecodeError, OSError) as e:
            parse_errors.append((rel, str(e)))
            continue
        if in_scope and args.fix and canonicalize_json_file(path):
            fixed.append(rel)

    exit_code = 0

    if parse_errors:
        for rel, err in parse_errors:
            print(f"{rel}: {err}", file=sys.stderr)
        print(
            f"\n{len(parse_errors)} of {count} JSON file(s) failed to parse.",
            file=sys.stderr,
        )
        exit_code = 1

    if args.fix:
        for rel in fixed:
            print(f"reformatted {rel}")
        print(f"{len(fixed)} file(s) reformatted.")
    elif offenders:
        for rel in offenders:
            print(f"{rel}: not canonical JSON", file=sys.stderr)
        print(
            f"\n{len(offenders)} data JSON file(s) are not canonical. "
            "Run `uv run python bin/lint-json.py --fix`.",
            file=sys.stderr,
        )
        exit_code = 1

    if exit_code == 0 and not args.fix:
        print(f"{count} JSON file(s) parse cleanly and data JSON is canonical.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
