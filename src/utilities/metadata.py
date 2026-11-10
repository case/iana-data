"""Metadata management for tracking download state."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)


def utc_timestamp() -> str:
    """Generate a UTC timestamp with second precision.

    Returns:
        Timestamp string in format: 2025-11-18T20:23:07Z
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def record_iptoasn_fetch(
    checked_at: str,
    downloaded_at: str | None = None,
    run_id: str | None = None,
) -> None:
    """Record an iptoasn artifact fetch, merging into any existing entry.

    Args:
        checked_at: When the caller recorded this fetch. A direct download
            passes its download time; the nightly passes the time after its
            build. Moves on every fetch.
        downloaded_at: When the artifact now in hand was obtained. Supplied only
            when the artifact fed the build, so a preserve night leaves the
            previous value in place, matching this file's convention that
            last_downloaded tracks content that reached the published data.
        run_id: The producer run behind ``downloaded_at``. Omitting it alongside
            ``downloaded_at`` clears any stored run id, because a direct download
            from upstream is not attributable to a producer run.

    Raises:
        ValueError: If ``run_id`` is given without ``downloaded_at``.
        OSError: If the entry is not on disk afterwards. ``save_metadata`` only
            logs a failed write, which its download callers rely on.
    """
    if run_id is not None and downloaded_at is None:
        raise ValueError("run_id needs downloaded_at; alone it names no artifact")

    metadata = load_metadata()
    entry = dict(metadata.get("IPTOASN", {}))
    entry["last_checked"] = checked_at
    if downloaded_at is not None:
        entry["last_downloaded"] = downloaded_at
        entry.pop("run_id", None)
        if run_id is not None:
            entry["run_id"] = run_id
    metadata["IPTOASN"] = entry
    save_metadata(metadata)
    if load_metadata().get("IPTOASN") != entry:
        raise OSError(f"IPTOASN metadata was not written to {METADATA_FILE}")


def save_metadata(metadata: MetadataDict) -> None:
    """Save metadata for future conditional requests."""
    metadata_path = Path(METADATA_FILE)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
            f.write("\n")
    except OSError as e:
        logger.error("Error saving metadata to %s: %s", metadata_path, e)
