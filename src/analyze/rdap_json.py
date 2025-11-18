"""Analysis for IANA RDAP Bootstrap JSON file."""

import logging
from pathlib import Path

from ..parse import parse_rdap_json

logger = logging.getLogger(__name__)


def analyze_rdap_json(filepath: Path) -> int:
    """
    Analyze and report on the RDAP Bootstrap JSON file.

    Args:
        filepath: Path to the RDAP JSON file

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if not filepath.exists():
        logger.error("File not found: %s", filepath)
        logger.info("Run --download first to fetch the data files")
        return 1

    rdap_lookup = parse_rdap_json(filepath)

    # Compute statistics
    total_tlds = len(rdap_lookup)
    unique_servers = set(rdap_lookup.values())

    logger.info("\033[1mRDAP Bootstrap Analysis:\033[0m")
    logger.info("  Total TLDs: %d", total_tlds)
    logger.info("  Unique RDAP Servers: %d", len(unique_servers))

    return 0
