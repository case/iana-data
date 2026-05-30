"""Utilities for content change detection and conditional writing."""

import json
import logging
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def canonical_json(data: Any, indent: int = 2) -> str:
    """The project's one canonical JSON serialization (no trailing newline)."""
    return json.dumps(data, indent=indent, ensure_ascii=False)


def _canonical_file(data: Any, indent: int = 2) -> str:
    """Canonical on-disk form: the JSON body plus the trailing newline."""
    return canonical_json(data, indent) + "\n"


def write_json_if_changed(
    filepath: Path | str,
    data: dict[str, Any],
    exclude_fields: list[str] | None = None,
    indent: int = 2,
) -> tuple[bool, str]:
    """
    Write JSON file only if its serialized output would differ, atomically.

    Compares serialized JSON (not parsed dicts) so key-order changes are
    detected. ``exclude_fields`` strips top-level keys (e.g. timestamps)
    before comparing. On change, writes via a same-directory temp file plus
    os.replace.

    Args:
        filepath: Path to JSON file to write
        data: New data to write
        exclude_fields: Top-level field names to exclude from comparison (e.g., ["publication"])
        indent: JSON indentation (default: 2)

    Returns:
        Tuple of (changed: bool, status: str)
        - changed: True if file was written, False if unchanged
        - status: "written" (new/changed), "unchanged", or "error"
    """
    filepath = Path(filepath)
    exclude_fields = exclude_fields or []

    # Check if file exists
    if not filepath.exists():
        try:
            _atomic_write_json(filepath, data, indent)
            logger.debug("Created new file: %s", filepath)
            return (True, "written")
        except Exception as e:
            logger.error("Error writing file %s: %s", filepath, e)
            return (False, "error")

    # Load existing file
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
    except Exception as e:
        logger.error("Error reading existing file %s: %s", filepath, e)
        # Treat as changed if we can't read existing file
        try:
            _atomic_write_json(filepath, data, indent)
            return (True, "written")
        except Exception as write_error:
            logger.error("Error writing file %s: %s", filepath, write_error)
            return (False, "error")

    new_data_compare = deepcopy(data)
    existing_data_compare = deepcopy(existing_data)

    for field in exclude_fields:
        new_data_compare.pop(field, None)
        existing_data_compare.pop(field, None)

    if canonical_json(new_data_compare, indent) == canonical_json(
        existing_data_compare, indent
    ):
        logger.debug(
            "Content unchanged for %s (excluding %s)", filepath, exclude_fields
        )
        return (False, "unchanged")

    # Content has changed - write new file atomically
    try:
        _atomic_write_json(filepath, data, indent)
        logger.debug("Updated file: %s", filepath)
        return (True, "written")
    except Exception as e:
        logger.error("Error writing file %s: %s", filepath, e)
        return (False, "error")


def _atomic_write_json(filepath: Path, data: dict[str, Any], indent: int) -> None:
    """Write JSON to filepath via a same-directory temp file + os.replace.

    The temp file lives in filepath's parent so the rename stays on one
    filesystem, where os.replace is documented atomic on POSIX and Windows.
    On any failure the temp file is removed; the original target is untouched.

    NamedTemporaryFile creates files with 0o600 by design. Generated data
    files in this project are read by other processes and CDNs; restore the
    umask-default 0o644 before the rename.
    """
    parent = filepath.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=filepath.name + ".",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = tmp.name
            tmp.write(_canonical_file(data, indent))
            # flush + fsync before close: os.replace is atomic for visibility,
            # but durability under power loss requires the bytes hit disk.
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, filepath)
        tmp_path = None
    finally:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)


def is_json_canonical(text: str, indent: int = 2) -> bool:
    """True if ``text`` already equals the canonical rendering of its own parse.

    Raises ``json.JSONDecodeError`` if ``text`` is not valid JSON.
    """
    return text == _canonical_file(json.loads(text), indent)


def canonicalize_json_file(path: Path, indent: int = 2) -> bool:
    """Rewrite ``path`` in canonical form if needed; return whether it changed.

    Reformatting only, never alters parsed data. Raises ``json.JSONDecodeError``
    on invalid JSON.
    """
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if text == _canonical_file(data, indent):
        return False
    _atomic_write_json(path, data, indent)
    return True
