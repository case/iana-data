"""Metadata management for tracking download state."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)


def utc_timestamp() -> str:
    """Generate a UTC timestamp with second precision.

    Returns:
        Timestamp string in format: 2025-11-18T20:23:07Z
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

GENERATED_DIR: Final[str] = "data/generated"
METADATA_FILE: Final[str] = f"{GENERATED_DIR}/metadata.json"

# Type alias for metadata structure
MetadataDict = dict[str, dict[str, Any]]


def load_metadata() -> MetadataDict:
    """Load metadata from previous downloads."""
    metadata_path = Path(METADATA_FILE)
    if metadata_path.exists():
        try:
            with open(metadata_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Error loading metadata from %s: %s", metadata_path, e)
            logger.info("Starting with empty metadata")
            return {}
    return {}


def save_metadata(metadata: MetadataDict) -> None:
    """Save metadata for future conditional requests."""
    metadata_path = Path(METADATA_FILE)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
    except OSError as e:
        logger.error("Error saving metadata to %s: %s", metadata_path, e)
