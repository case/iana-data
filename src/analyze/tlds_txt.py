"""Analysis for IANA TLDs text file."""

import logging
from pathlib import Path

from ..parse import parse_tlds_txt

logger = logging.getLogger(__name__)


def get_tlds_analysis(filepath: Path) -> dict[str, int]:
    """
    Get analysis data for the TLDs text file.

    Args:
        filepath: Path to the TLDs text file

    Returns:
        Dict with analysis results:
        - total: Total number of TLDs
        - idns: Number of internationalized domain names (xn--)
    """
    tlds = parse_tlds_txt(filepath)

    # Count IDNs (start with "xn--" or "XN--")
    idns = [tld for tld in tlds if tld.upper().startswith("XN--")]

    return {
        "total": len(tlds),
        "idns": len(idns),
    }


def analyze_tlds_txt(filepath: Path) -> int:
    """
    Analyze and report on the TLDs text file.

    Args:
        filepath: Path to the TLDs text file

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if not filepath.exists():
        logger.error("File not found: %s", filepath)
        logger.info("Run --download first to fetch the data files")
        return 1

    results = get_tlds_analysis(filepath)

    logger.info("\033[1mTLD List Analysis:\033[0m")
    logger.info("  Total TLDs: %d", results["total"])
    logger.info("  IDNs (xn--): %d", results["idns"])

    return 0
