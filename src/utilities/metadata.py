"""Metadata management for tracking download state."""

import json
from pathlib import Path
from typing import Final

GENERATED_DIR: Final[str] = "data/generated"
METADATA_FILE: Final[str] = f"{GENERATED_DIR}/metadata.json"


def load_metadata() -> dict[str, dict[str, str]]:
    """Load metadata from previous downloads."""
    metadata_path = Path(METADATA_FILE)
    if metadata_path.exists():
        with open(metadata_path, "r") as f:
            return json.load(f)
    return {}


def save_metadata(metadata: dict[str, dict[str, str]]) -> None:
    """Save metadata for future conditional requests."""
    metadata_path = Path(METADATA_FILE)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
