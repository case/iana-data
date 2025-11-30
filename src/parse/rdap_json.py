"""Parser for IANA RDAP Bootstrap JSON file."""

import json
import logging
from pathlib import Path

from ..config import SOURCE_DIR, SOURCE_FILES
from ..utilities.file_io import read_json_file

logger = logging.getLogger(__name__)


def parse_rdap_json(filepath: Path | None = None) -> dict[str, str]:
    """
    Parse the RDAP Bootstrap JSON file into a TLD lookup map.

    Args:
        filepath: Path to the RDAP JSON file (defaults to configured location)

    Returns:
        dict: Map of TLD (ASCII, without leading dot) to RDAP server URL
    """
    if filepath is None:
        filepath = Path(SOURCE_DIR) / SOURCE_FILES["RDAP_BOOTSTRAP"]

    data = read_json_file(filepath, default={})

    rdap_map = {}
    for service in data.get("services", []):
        tlds = service[0]
        servers = service[1]
        # Use first server for each TLD
        server_url = servers[0] if servers else None
        if server_url:
            for tld in tlds:
                # Remove leading dot if present
                clean_tld = tld.lstrip(".")
                rdap_map[clean_tld] = server_url

    return rdap_map


def rdap_json_content_changed(filepath: Path, new_content: str) -> bool:
    """
    Check if RDAP JSON content has actually changed.

    Ignores publication timestamp - only compares actual services data.

    Args:
        filepath: Path to existing RDAP file
        new_content: New content to compare against

    Returns:
        True if content changed, False if only timestamp changed
    """
    if not filepath.exists():
        return True

    # Parse new content
    try:
        new_data = json.loads(new_content)
        new_services = new_data.get("services", [])
    except json.JSONDecodeError as e:
        logger.error("Error parsing new RDAP content: %s", e)
        return True  # Treat as changed if we can't parse

    # Parse existing content
    existing_data = read_json_file(filepath, default={})
    if not existing_data:
        # File couldn't be read or parsed
        return True
    existing_services = existing_data.get("services", [])

    # Only consider changed if services differ (ignore publication timestamp)
    if new_services == existing_services:
        logger.info("RDAP content unchanged (only timestamp updated)")
        return False

    return True
