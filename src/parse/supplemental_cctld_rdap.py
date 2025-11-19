"""Parser for supplemental ccTLD RDAP data."""

import json
import logging
from pathlib import Path

from ..config import MANUAL_DIR

logger = logging.getLogger(__name__)


def parse_supplemental_cctld_rdap(filepath: Path | None = None) -> dict[str, dict]:
    """
    Parse supplemental ccTLD RDAP data file.

    Args:
        filepath: Path to supplemental RDAP JSON file (defaults to configured location)

    Returns:
        dict: Map of TLD (ASCII, without leading dot) to dict with:
            - rdap_server: RDAP server URL
            - source: Source URL where the RDAP server was found
    """
    if filepath is None:
        filepath = Path(MANUAL_DIR) / "supplemental-cctld-rdap.json"

    if not filepath.exists():
        return {}

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Error parsing supplemental RDAP from %s: %s", filepath, e)
        return {}

    # Build lookup map
    supplemental_map = {}
    for entry in data.get("ccTldRdapServers", []):
        tld = entry.get("tld", "").lstrip(".")
        rdap_server = entry.get("rdapServer")
        source = entry.get("source")
        if tld and rdap_server:
            supplemental_map[tld] = {
                "rdap_server": rdap_server,
                "source": source,
            }

    return supplemental_map
