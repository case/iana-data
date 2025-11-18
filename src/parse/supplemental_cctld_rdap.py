"""Parser for supplemental ccTLD RDAP data."""

import json
from pathlib import Path

from ..config import GENERATED_DIR


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
        filepath = Path(GENERATED_DIR) / "supplemental-cctld-rdap.json"

    if not filepath.exists():
        return {}

    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

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
