"""Utilities for content change detection and conditional writing."""

import json
import logging
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_json_if_changed(
    filepath: Path | str,
    data: dict[str, Any],
    exclude_fields: list[str] | None = None,
    indent: int = 2,
) -> tuple[bool, str]:
    """
    Write JSON file only if content has actually changed, atomically.

    Compares new data with existing file, ignoring specified fields
    (typically timestamps). If content is unchanged, keeps the existing
    file and timestamp. If content has changed, writes via a same-directory
    temp file plus os.replace so a mid-write failure cannot leave a torn
    or truncated file on disk.

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

    # Compare content, excluding specified fields
    new_data_compare = deepcopy(data)
    existing_data_compare = deepcopy(existing_data)

    for field in exclude_fields:
        new_data_compare.pop(field, None)
        existing_data_compare.pop(field, None)

    if new_data_compare == existing_data_compare:
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
            json.dump(data, tmp, indent=indent, ensure_ascii=False)
            tmp.write("\n")
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
