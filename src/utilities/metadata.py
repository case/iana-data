"""Metadata management for tracking download state."""

import json
import logging
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

GENERATED_DIR: Final[str] = "data/generated"
METADATA_FILE: Final[str] = f"{GENERATED_DIR}/metadata.json"


def load_metadata() -> dict[str, dict[str, str]]:
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


def save_metadata(metadata: dict[str, dict[str, str]]) -> None:
    """Save metadata for future conditional requests."""
    metadata_path = Path(METADATA_FILE)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
    except OSError as e:
        logger.error("Error saving metadata to %s: %s", metadata_path, e)
