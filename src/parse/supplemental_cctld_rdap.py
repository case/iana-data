"""Parser for supplemental ccTLD RDAP data."""

import logging
from pathlib import Path

from ..config import MANUAL_DIR
from ..utilities.file_io import read_json_file

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

    data = read_json_file(filepath, default={})

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
