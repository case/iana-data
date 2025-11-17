"""Analysis for IANA Root Zone Database HTML file."""

import logging
from pathlib import Path

from ..parse import parse_root_db_html

logger = logging.getLogger(__name__)


def analyze_root_db_html(filepath: Path) -> int:
    """
    Analyze and report on the Root Zone Database HTML file.

    Args:
        filepath: Path to the root zone HTML file

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if not filepath.exists():
        logger.error("File not found: %s", filepath)
        logger.info("Run --download first to fetch the data files")
        return 1

    results = parse_root_db_html(filepath)

    logger.info("\033[1mRoot Zone Database Analysis:\033[0m")
    logger.info("  Total TLDs: %d", results["total"])
    logger.info("")
    logger.info("  Delegated:")
    logger.info("    Total: %d", results["delegated"]["total"])
    logger.info("    Unique TLD Managers: %d", results["delegated"]["unique_managers"])
    logger.info("      Unique gTLD Managers: %d", results["delegated"]["unique_gtld_managers"])
    logger.info("      Unique ccTLD Managers: %d", results["delegated"]["unique_cctld_managers"])
    logger.info("")
    logger.info("    IDN Statistics:")
    logger.info("      Total IDNs: %d", results["delegated"]["total_idns"])
    for tld_type, count in sorted(results["delegated"]["idn_by_type"].items()):
        logger.info("        %s IDNs: %d", tld_type, count)
    logger.info("")
    logger.info("    By Type:")

    # Show Generic total with subtypes
    logger.info("      Generic: %d", results["delegated"]["total_generic"])
    generic_types = ["generic", "sponsored", "infrastructure", "generic-restricted"]
    for generic_type in generic_types:
        if generic_type in results["delegated"]["by_type"]:
            logger.info("        %s: %d", generic_type, results["delegated"]["by_type"][generic_type])

    # Show Country-code
    if "country-code" in results["delegated"]["by_type"]:
        logger.info("      Country-code: %d", results["delegated"]["by_type"]["country-code"])
    logger.info("")
    logger.info("  Undelegated:")
    logger.info("    Total: %d", results["undelegated"]["total"])

    return 0
