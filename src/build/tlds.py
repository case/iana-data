"""Build enhanced TLD data file."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import IANA_URLS, TLD_PAGES_DIR, TLDS_OUTPUT_FILE
from ..parse.rdap_json import parse_rdap_json
from ..parse.root_db_html import derive_type_from_iana_tag, parse_root_db_html
from ..parse.supplemental_cctld_rdap import parse_supplemental_cctld_rdap
from ..parse.tld_html import parse_tld_page
from ..utilities.urls import get_tld_file_path

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

    # Load and parse TLD pages
    logger.info("Parsing TLD pages...")
    tld_pages_dir = Path(TLD_PAGES_DIR)
    tld_page_data: dict[str, dict[str, Any]] = {}

    for entry in root_zone_entries:
        tld = entry["domain"].lstrip(".")
        file_path = get_tld_file_path(tld, tld_pages_dir)

        if file_path.exists():
            try:
                html = file_path.read_text(encoding="utf-8")
                tld_page_data[tld] = parse_tld_page(html)
            except Exception as e:
                logger.warning("Error parsing TLD page for %s: %s", tld, e)

    logger.info("Parsed %d TLD pages", len(tld_page_data))

    # Build TLD entries
    logger.info("Building TLD entries...")
    tlds = []
    for entry in root_zone_entries:
        tld = entry["domain"].lstrip(".")
        page_data = tld_page_data.get(tld, {})
        tld_entry = _build_tld_entry(entry, rdap_lookup, supplemental_rdap, page_data)
        tlds.append(tld_entry)

    # Build IDN ↔ ASCII bidirectional mapping
    logger.info("Building IDN mappings...")
    _add_idn_mappings(tlds)

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
    page_data: dict[str, Any],
) -> dict:
    """
    Build a single TLD entry for output.

    Args:
        root_zone_entry: Entry from root zone parser
        rdap_lookup: Map of TLD to IANA RDAP server URL
        supplemental_rdap: Map of TLD to supplemental RDAP data
        page_data: Parsed data from TLD detail page

    Returns:
        dict: TLD entry following schema
    """
    tld = root_zone_entry["domain"].lstrip(".")
    tld_manager = root_zone_entry["manager"]
    iana_tag = root_zone_entry["type"]

    # Build core fields
    entry: dict[str, Any] = {
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

    # Add tld_iso for IDN ccTLDs (from page data)
    if "tld_iso" in page_data:
        entry["tld_iso"] = page_data["tld_iso"]

    # Add delegated status
    entry["delegated"] = tld_manager != "Not assigned"

    # Add IANA tag
    entry["iana_tag"] = iana_tag

    # Derive type from IANA tag
    entry["type"] = derive_type_from_iana_tag(iana_tag)

    # Build orgs object
    orgs: dict[str, str] = {}
    if tld_manager != "Not assigned":
        orgs["tld_manager"] = tld_manager

    if "orgs" in page_data:
        if "admin" in page_data["orgs"]:
            orgs["admin"] = page_data["orgs"]["admin"]
        if "tech" in page_data["orgs"]:
            orgs["tech"] = page_data["orgs"]["tech"]

    if orgs:
        entry["orgs"] = orgs

    # Add nameservers from page data
    if "nameservers" in page_data:
        entry["nameservers"] = page_data["nameservers"]

    # Add registry information
    if "registry_url" in page_data:
        entry["registry_url"] = page_data["registry_url"]

    if "whois_server" in page_data:
        entry["whois_server"] = page_data["whois_server"]

    # Add RDAP server - prefer page data, then IANA, then supplemental
    rdap_server = None
    rdap_source = None

    if "rdap_server" in page_data:
        rdap_server = page_data["rdap_server"]
        rdap_source = "IANA"
    elif tld in rdap_lookup:
        rdap_server = rdap_lookup[tld]
        rdap_source = "IANA"
    elif tld in supplemental_rdap:
        rdap_server = supplemental_rdap[tld]["rdap_server"]
        rdap_source = supplemental_rdap[tld]["source"]

    if rdap_server:
        entry["rdap_server"] = rdap_server

    # Add dates from page data
    if "tld_created" in page_data:
        entry["tld_created"] = page_data["tld_created"]

    if "tld_updated" in page_data:
        entry["tld_updated"] = [page_data["tld_updated"]]

    # Add IANA reports from page data
    if "iana_reports" in page_data:
        entry["iana_reports"] = page_data["iana_reports"]

    # Add annotations if needed
    if rdap_source:
        entry["annotations"] = {
            "rdap_source": rdap_source,
        }

    return entry


def _add_idn_mappings(tlds: list[dict]) -> None:
    """
    Add bidirectional IDN ↔ ASCII ccTLD mappings.

    For each IDN ccTLD with tld_iso, add the IDN to the corresponding
    ASCII ccTLD's idn array.

    Args:
        tlds: List of TLD entries (modified in place)
    """
    # Build lookup by TLD
    tld_lookup = {entry["tld"]: entry for entry in tlds}

    # Find all IDN ccTLDs with tld_iso and group by ASCII equivalent
    idn_mappings: dict[str, list[str]] = {}
    for entry in tlds:
        if "tld_iso" in entry:
            ascii_tld = entry["tld_iso"]
            if ascii_tld not in idn_mappings:
                idn_mappings[ascii_tld] = []
            idn_mappings[ascii_tld].append(entry["tld"])

    # Add idn array to ASCII ccTLDs
    for ascii_tld, idn_list in idn_mappings.items():
        if ascii_tld in tld_lookup:
            tld_lookup[ascii_tld]["idn"] = sorted(idn_list)
