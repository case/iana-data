"""Tests for bin/lint-json.py scoping logic.

bin/ is not an importable package, so the script is loaded by path; main() is
guarded by __main__, so importing only adjusts sys.path and pulls helpers.
"""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "bin" / "lint-json.py"
_spec = importlib.util.spec_from_file_location("lint_json", _SCRIPT)
assert _spec is not None and _spec.loader is not None
lint_json = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint_json)


def test_in_format_scope_includes_manual_and_generated():
    assert lint_json.in_format_scope(Path("data/manual/places.json")) is True
    assert lint_json.in_format_scope(Path("data/generated/places.json")) is True


def test_in_format_scope_includes_nested_generated():
    assert lint_json.in_format_scope(Path("data/generated/tld/aaa.json")) is True


def test_in_format_scope_excludes_source():
    # Verbatim upstream captures must never be reformatted.
    assert lint_json.in_format_scope(Path("data/source/iana-rdap.json")) is False


def test_in_format_scope_excludes_unrelated_json():
    assert lint_json.in_format_scope(Path("package.json")) is False
    assert (
        lint_json.in_format_scope(Path("tests/fixtures/source/core/rdap.json")) is False
    )
