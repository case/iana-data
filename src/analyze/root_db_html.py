"""Analysis for IANA Root Zone Database HTML file."""

import logging
from collections import defaultdict
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

    entries = parse_root_db_html(filepath)

    # Compute statistics
    delegated_entries = [e for e in entries if e.get("delegated", True)]
    undelegated_entries = [e for e in entries if not e.get("delegated", True)]

    # Count delegated by type
    delegated_by_type = defaultdict(int)
    for entry in delegated_entries:
        delegated_by_type[entry["type"]] += 1

    # Calculate total generic types (generic + sponsored + infrastructure + generic-restricted)
    generic_types = ["generic", "sponsored", "infrastructure", "generic-restricted"]
    delegated_total_generic = sum(delegated_by_type.get(t, 0) for t in generic_types)

    # Count delegated IDNs (domains starting with .xn--)
    delegated_idn_entries = [e for e in delegated_entries if e.get("domain", "").startswith(".xn--")]
    delegated_total_idns = len(delegated_idn_entries)

    # Count delegated IDNs by type
    delegated_idn_by_type = defaultdict(int)
    for entry in delegated_idn_entries:
        delegated_idn_by_type[entry["type"]] += 1

    # Count unique managers for delegated TLDs
    unique_managers = set(entry["manager"] for entry in delegated_entries)
    total_unique_managers = len(unique_managers)

    # Count unique gTLD managers (generic types)
    gtld_managers = set(
        entry["manager"]
        for entry in delegated_entries
        if entry["type"] in generic_types
    )
    total_unique_gtld_managers = len(gtld_managers)

    # Count unique ccTLD managers (country-code)
    cctld_managers = set(
        entry["manager"]
        for entry in delegated_entries
        if entry["type"] == "country-code"
    )
    total_unique_cctld_managers = len(cctld_managers)

    # Report results
    logger.info("\033[1mRoot Zone Database Analysis:\033[0m")
    logger.info("  Total TLDs: %d", len(entries))
    logger.info("")
    logger.info("  Delegated:")
    logger.info("    Total: %d", len(delegated_entries))
    logger.info("    Unique TLD Managers: %d", total_unique_managers)
    logger.info("      Unique gTLD Managers: %d", total_unique_gtld_managers)
    logger.info("      Unique ccTLD Managers: %d", total_unique_cctld_managers)
    logger.info("")
    logger.info("    IDN Statistics:")
    logger.info("      Total IDNs: %d", delegated_total_idns)
    for tld_type, count in sorted(delegated_idn_by_type.items()):
        logger.info("        %s IDNs: %d", tld_type, count)
    logger.info("")
    logger.info("    By Type:")

    # Show Generic total with subtypes
    logger.info("      Generic: %d", delegated_total_generic)
    for generic_type in generic_types:
        if generic_type in delegated_by_type:
            logger.info("        %s: %d", generic_type, delegated_by_type[generic_type])

    # Show Country-code
    if "country-code" in delegated_by_type:
        logger.info("      Country-code: %d", delegated_by_type["country-code"])
    logger.info("")
    logger.info("  Undelegated:")
    logger.info("    Total: %d", len(undelegated_entries))

    return 0
