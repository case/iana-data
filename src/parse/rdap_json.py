"""Parser for IANA RDAP Bootstrap JSON file."""

import json
from pathlib import Path

from ..config import SOURCE_DIR, SOURCE_FILES


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
    content = filepath.read_text()
    data = json.loads(content)

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
