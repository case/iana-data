"""Parser for AS organization aliases data."""

import logging
from pathlib import Path

from ..config import MANUAL_DIR, MANUAL_FILES
from ..utilities.file_io import read_json_file

logger = logging.getLogger(__name__)


def parse_as_org_aliases(filepath: Path | None = None) -> dict[str, str]:
    """
    Parse AS org aliases file and return a reverse lookup.

    The aliases file maps canonical names (e.g., "CentralNic") to
    arrays of AS organization names. This function reverses that mapping,
    returning a dict from AS org name to canonical alias.

    Args:
        filepath: Path to aliases JSON file (defaults to configured location)

    Returns:
        dict: Map of AS org name to canonical alias name.
              E.g., {"CENTRALNIC-ANYCAST-A CentralNic Anycast-A AS Number": "CentralNic"}
    """
    if filepath is None:
        filepath = Path(MANUAL_DIR) / MANUAL_FILES["AS_ORG_ALIASES"]

    data = read_json_file(filepath, default={})

    # Build reverse lookup: AS org name -> canonical alias
    aliases_lookup: dict[str, str] = {}
    for alias, entries in data.get("asOrgAliases", {}).items():
        for entry in entries:
            name = entry.get("name")
            if name:
                aliases_lookup[name] = alias

    return aliases_lookup
