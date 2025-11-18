"""Build enhanced TLD data file."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..config import IANA_URLS, TLDS_OUTPUT_FILE
from ..parse.rdap_json import parse_rdap_json
from ..parse.root_db_html import derive_type_from_iana_tag, parse_root_db_html
from ..parse.supplemental_cctld_rdap import parse_supplemental_cctld_rdap

logger = logging.getLogger(__name__)


def build_tlds_json() -> dict:
    """
    Build enhanced TLD data file aggregating IANA sources.

    Returns:
        dict: Result summary with counts
    """
    # Parse source files
    logger.info("Parsing source files...")
    root_zone_entries = parse_root_db_html()
    rdap_lookup = parse_rdap_json()
    supplemental_rdap = parse_supplemental_cctld_rdap()

    # Build TLD entries
    logger.info("Building TLD entries...")
    tlds = []
    for entry in root_zone_entries:
        tld_entry = _build_tld_entry(entry, rdap_lookup, supplemental_rdap)
        tlds.append(tld_entry)

    # Build output structure
    output = {
        "description": "Enhanced TLD bootstrap data, from IANA sources",
        "publication": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "iana_root_db": IANA_URLS["ROOT_ZONE_DB"],
            "iana_rdap": IANA_URLS["RDAP_BOOTSTRAP"],
        },
        "tlds": tlds,
    }

    # Write output file
    output_path = Path(TLDS_OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Writing output to {output_path}...")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.error("Error writing output to %s: %s", output_path, e)
        return {
            "total_tlds": len(tlds),
            "output_file": None,
            "error": str(e),
        }

    logger.info(f"Successfully built {len(tlds)} TLD entries")
    return {
        "total_tlds": len(tlds),
        "output_file": str(output_path),
    }


def _build_tld_entry(
    root_zone_entry: dict,
    rdap_lookup: dict[str, str],
    supplemental_rdap: dict[str, dict],
) -> dict:
    """
    Build a single TLD entry for output.

    Args:
        root_zone_entry: Entry from root zone parser
        rdap_lookup: Map of TLD to IANA RDAP server URL
        supplemental_rdap: Map of TLD to supplemental RDAP data

    Returns:
        dict: TLD entry following schema
    """
    tld = root_zone_entry["domain"].lstrip(".")
    tld_manager = root_zone_entry["manager"]
    iana_tag = root_zone_entry["type"]

    # Build core fields
    entry = {
        "tld": tld,
    }

    # Add tld_unicode for IDNs
    if tld.startswith("xn--"):
        try:
            tld_unicode = tld.encode("ascii").decode("idna")
            entry["tld_unicode"] = tld_unicode
        except Exception:
            # If decoding fails, skip unicode field
            pass

    # Add delegated status
    entry["delegated"] = tld_manager != "Not assigned"

    # Add IANA tag
    entry["iana_tag"] = iana_tag

    # Derive type from IANA tag
    entry["type"] = derive_type_from_iana_tag(iana_tag)

    # Add TLD manager
    entry["tld_manager"] = tld_manager

    # Add RDAP server and annotations if available
    rdap_server = None
    rdap_source = None

    # Check IANA RDAP first
    if tld in rdap_lookup:
        rdap_server = rdap_lookup[tld]
        rdap_source = "IANA"

    # Check supplemental RDAP if no IANA RDAP
    if not rdap_server and tld in supplemental_rdap:
        rdap_server = supplemental_rdap[tld]["rdap_server"]
        rdap_source = supplemental_rdap[tld]["source"]

    # Add RDAP server if available
    if rdap_server:
        entry["rdap_server"] = rdap_server

    # Add annotations if needed
    if rdap_source:
        entry["annotations"] = {
            "rdap_source": rdap_source,
        }

    return entry
