"""Utilities for content change detection and conditional writing."""

import json
import logging
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
    Write JSON file only if content has actually changed.

    Compares new data with existing file, ignoring specified fields
    (typically timestamps). If content is unchanged, keeps the existing
    file and timestamp. If content changed, writes new file with updated
    timestamp.

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
        # New file - write it
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
                f.write("\n")  # Add trailing newline
            logger.info("Created new file: %s", filepath)
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
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
                f.write("\n")
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
        logger.info("Content unchanged for %s (excluding %s)", filepath, exclude_fields)
        return (False, "unchanged")

    # Content has changed - write new file
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.write("\n")
        logger.info("Updated file: %s", filepath)
        return (True, "written")
    except Exception as e:
        logger.error("Error writing file %s: %s", filepath, e)
        return (False, "error")
