"""Parser for orgs.tech aliases data."""

import logging
from pathlib import Path

from ..config import MANUAL_DIR, MANUAL_FILES
from ..utilities.file_io import read_json_file

logger = logging.getLogger(__name__)


def parse_tech_aliases(filepath: Path | None = None) -> dict[str, str]:
    """
    Parse tech aliases file and return a reverse lookup.

    The aliases file maps canonical names (e.g., "Identity Digital") to
    arrays of orgs.tech names. This function reverses that mapping,
    returning a dict from orgs.tech name to canonical alias.

    Args:
        filepath: Path to aliases JSON file (defaults to configured location)

    Returns:
        dict: Map of orgs.tech name to canonical alias name.
              E.g., {"Identity Digital Limited": "Identity Digital"}
    """
    if filepath is None:
        filepath = Path(MANUAL_DIR) / MANUAL_FILES["TECH_ALIASES"]

    data = read_json_file(filepath, default={})

    # Build reverse lookup: orgs.tech name -> canonical alias
    aliases_lookup: dict[str, str] = {}
    for alias, entries in data.get("techAliases", {}).items():
        for entry in entries:
            name = entry.get("name")
            if name:
                aliases_lookup[name] = alias

    return aliases_lookup
