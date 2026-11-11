"""Centralized file I/O utilities with error handling."""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import overload

logger = logging.getLogger(__name__)


@overload
def read_json_file(filepath: Path, default: dict) -> dict: ...


@overload
def read_json_file(filepath: Path, default: list) -> list: ...


@overload
def read_json_file(filepath: Path, default: None = None) -> dict: ...


def read_json_file(filepath: Path, default: dict | list | None = None) -> dict | list:
    """Read and parse a JSON file with error handling.

    Args:
        filepath: Path to the JSON file to read
        default: Value to return if file cannot be read or parsed.
                If None, returns empty dict.

    Returns:
        Parsed JSON data as dict or list, or default value on error
    """
    if default is None:
        default = {}

    try:
        content = filepath.read_text()
        return json.loads(content)
    except OSError as e:
        logger.error("Error reading file %s: %s", filepath, e)
        return default
    except json.JSONDecodeError as e:
        logger.error("Error parsing JSON from %s: %s", filepath, e)
        return default


def read_text_file(filepath: Path, default: str = "") -> str:
    """Read a text file with error handling.

    Args:
        filepath: Path to the text file to read
        default: Value to return if file cannot be read

    Returns:
        File contents as string, or default value on error
    """
    try:
        return filepath.read_text()
    except OSError as e:
        logger.error("Error reading file %s: %s", filepath, e)
        return default


def atomic_write_bytes(filepath: Path, content: bytes) -> None:
    """Replace ``filepath`` with ``content`` through a same-directory temp file.

    The original is untouched on failure, and the temp file is removed.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=filepath.parent,
            prefix=filepath.name + ".",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = tmp.name
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        # NamedTemporaryFile creates 0o600; source files are world-readable.
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, filepath)
        tmp_path = None
    finally:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)
