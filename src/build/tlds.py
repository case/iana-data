"""Build enhanced TLD data file."""

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import IANA_URLS, IDN_SCRIPT_MAPPING_FILE, TLD_PAGES_DIR, TLDS_OUTPUT_FILE
from ..parse.country import get_country_name, is_cctld
from ..parse.iptoasn import ASNLookup
from ..parse.rdap_json import parse_rdap_json
from ..utilities.download import get_iptoasn_path
from ..parse.registry_agreement_csv import (
    RegistryAgreement,
    get_normalized_agreement_types,
    parse_registry_agreement_csv,
)
from ..parse.root_db_html import derive_type_from_iana_tag, parse_root_db_html
from ..parse.supplemental_cctld_rdap import parse_supplemental_cctld_rdap
from ..parse.tld_html import parse_tld_page
from ..parse.as_org_aliases import parse_as_org_aliases
from ..parse.tld_manager_aliases import parse_tld_manager_aliases
from ..utilities.content_changed import write_json_if_changed
from ..utilities.metadata import load_metadata, save_metadata, utc_timestamp
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
    registry_agreements = parse_registry_agreement_csv()
    tld_manager_aliases = parse_tld_manager_aliases()
    as_org_aliases = parse_as_org_aliases()

    # Load IDN script mappings
    idn_script_mapping = {}
    idn_script_file = Path(IDN_SCRIPT_MAPPING_FILE)
    if idn_script_file.exists():
        try:
            with open(idn_script_file, "r", encoding="utf-8") as f:
                idn_script_mapping = json.load(f)
            logger.info("Loaded %d IDN script mappings", len(idn_script_mapping))
        except Exception as e:
            logger.warning("Error loading IDN script mappings: %s", e)

    # Load iptoasn data for ASN lookups
    asn_lookup: ASNLookup | None = None
    iptoasn_path = get_iptoasn_path()
    if iptoasn_path.exists():
        try:
            logger.info("Loading iptoasn data from %s...", iptoasn_path)
            records = _parse_gzipped_iptoasn(iptoasn_path)
            asn_lookup = ASNLookup(records)
            logger.info("Loaded %d ASN records", len(records))
            # Update metadata to track when iptoasn data was used
            metadata = load_metadata()
            metadata["IPTOASN"] = {
                "last_downloaded": utc_timestamp(),
            }
            save_metadata(metadata)
        except Exception as e:
            logger.warning("Error loading iptoasn data: %s", e)
    else:
        logger.info("No iptoasn data found at %s (run 'make download-iptoasn' to enable ASN lookups)", iptoasn_path)

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
        tld_entry = _build_tld_entry(
            entry,
            rdap_lookup,
            supplemental_rdap,
            page_data,
            idn_script_mapping,
            registry_agreements,
            tld_manager_aliases,
            as_org_aliases,
            asn_lookup,
        )
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

    # Write output file (only if content changed)
    output_path = Path(TLDS_OUTPUT_FILE)
    logger.info(f"Writing output to {output_path}...")

    changed, status = write_json_if_changed(
        output_path,
        output,
        exclude_fields=["publication"],
        indent=2,
    )

    if status == "error":
        return {
            "total_tlds": len(tlds),
            "output_file": None,
            "changed": False,
            "error": "Failed to write file",
        }

    logger.info(f"Successfully built {len(tlds)} TLD entries")
    return {
        "total_tlds": len(tlds),
        "output_file": str(output_path),
        "file_size": output_path.stat().st_size,
        "changed": changed,
    }


def _build_tld_entry(
    root_zone_entry: dict,
    rdap_lookup: dict[str, str],
    supplemental_rdap: dict[str, dict],
    page_data: dict[str, Any],
    idn_script_mapping: dict[str, str],
    registry_agreements: dict[str, RegistryAgreement],
    tld_manager_aliases: dict[str, str],
    as_org_aliases: dict[str, str],
    asn_lookup: ASNLookup | None,
) -> dict:
    """
    Build a single TLD entry for output.

    Args:
        root_zone_entry: Entry from root zone parser
        rdap_lookup: Map of TLD to IANA RDAP server URL
        supplemental_rdap: Map of TLD to supplemental RDAP data
        page_data: Parsed data from TLD detail page
        idn_script_mapping: Map of IDN TLD to script name
        registry_agreements: Map of TLD to ICANN registry agreement data
        tld_manager_aliases: Map of TLD manager name to canonical alias
        as_org_aliases: Map of AS org name to canonical alias
        asn_lookup: Optional ASNLookup for IP-to-ASN resolution

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

    # Add tld_script for IDNs
    if tld in idn_script_mapping:
        entry["tld_script"] = idn_script_mapping[tld]

    # Add tld_iso for IDN ccTLDs (from page data)
    if "tld_iso" in page_data:
        entry["tld_iso"] = page_data["tld_iso"]

    # Add delegated status
    entry["delegated"] = tld_manager != "Not assigned"

    # Add IANA tag
    entry["iana_tag"] = iana_tag

    # Derive type from IANA tag
    entry["type"] = derive_type_from_iana_tag(iana_tag)

    # Build orgs object (canonical data only)
    orgs: dict[str, str] = {}
    tld_manager_alias = None
    if tld_manager != "Not assigned":
        orgs["tld_manager"] = tld_manager
        # Track alias for annotations (non-canonical, manually curated)
        if tld_manager in tld_manager_aliases:
            tld_manager_alias = tld_manager_aliases[tld_manager]

    if "orgs" in page_data:
        if "admin" in page_data["orgs"]:
            orgs["admin"] = page_data["orgs"]["admin"]
        if "tech" in page_data["orgs"]:
            orgs["tech"] = page_data["orgs"]["tech"]

    if orgs:
        entry["orgs"] = orgs

    # Add nameservers from page data (with ASN enrichment if available)
    # Also collect unique AS org aliases for annotations
    as_org_aliases_found: set[str] = set()
    if "nameservers" in page_data:
        entry["nameservers"] = _enrich_nameservers_with_asn(
            page_data["nameservers"],
            asn_lookup,
            as_org_aliases,
            as_org_aliases_found,
        )

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
        rdap_source = "supplemental"

    if rdap_server:
        entry["rdap_server"] = rdap_server

    # Add dates from page data
    if "tld_created" in page_data:
        entry["tld_created"] = page_data["tld_created"]

    if "tld_updated" in page_data:
        entry["tld_updated"] = [page_data["tld_updated"]]

    # Add annotations if needed (non-canonical / derived data)
    annotations: dict[str, str | list[str]] = {}

    if tld_manager_alias:
        annotations["tld_manager_alias"] = tld_manager_alias

    if rdap_source:
        annotations["rdap_source"] = rdap_source

    # Add country name for ccTLDs (both ASCII and IDN)
    if is_cctld(tld):
        # ASCII ccTLD - look up directly
        country_name = get_country_name(tld)
        if country_name:
            annotations["country_name_iso"] = country_name
    elif "tld_iso" in entry:
        # IDN ccTLD - look up by the ISO code
        country_name = get_country_name(entry["tld_iso"])
        if country_name:
            annotations["country_name_iso"] = country_name

    # Add registry agreement types from ICANN data (gTLDs only)
    if tld in registry_agreements:
        agreement = registry_agreements[tld]
        agreement_types = get_normalized_agreement_types(agreement.get("agreement_types", []))
        if agreement_types:
            annotations["registry_agreement_types"] = agreement_types

    # Add AS org aliases for nameserver infrastructure
    if as_org_aliases_found:
        annotations["as_org_aliases"] = sorted(as_org_aliases_found)

    if annotations:
        entry["annotations"] = annotations

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


def _enrich_nameservers_with_asn(
    nameservers: list[dict[str, Any]],
    asn_lookup: ASNLookup | None,
    as_org_aliases: dict[str, str],
    as_org_aliases_found: set[str],
) -> list[dict[str, Any]]:
    """
    Transform nameserver IP strings to objects with ASN metadata.

    Args:
        nameservers: List of nameserver dicts with hostname, ipv4, ipv6 arrays
        asn_lookup: Optional ASNLookup for IP-to-ASN resolution
        as_org_aliases: Map of AS org name to canonical alias
        as_org_aliases_found: Set to collect found aliases (modified in place)

    Returns:
        Transformed nameservers with IP objects containing ASN data
    """
    result = []

    for ns in nameservers:
        enriched_ns: dict[str, Any] = {
            "hostname": ns["hostname"],
            "ipv4": [],
            "ipv6": [],
        }

        # Transform IPv4 addresses
        for ip in ns.get("ipv4", []):
            ip_obj = _ip_to_asn_object(ip, asn_lookup)
            enriched_ns["ipv4"].append(ip_obj)
            # Collect AS org alias if found
            as_org = ip_obj.get("as_org", "")
            if as_org in as_org_aliases:
                as_org_aliases_found.add(as_org_aliases[as_org])

        # Transform IPv6 addresses
        for ip in ns.get("ipv6", []):
            ip_obj = _ip_to_asn_object(ip, asn_lookup)
            enriched_ns["ipv6"].append(ip_obj)
            # Collect AS org alias if found
            as_org = ip_obj.get("as_org", "")
            if as_org in as_org_aliases:
                as_org_aliases_found.add(as_org_aliases[as_org])

        result.append(enriched_ns)

    return result


def _ip_to_asn_object(ip: str, asn_lookup: ASNLookup | None) -> dict[str, Any]:
    """
    Convert an IP string to an object with ASN metadata.

    Args:
        ip: IP address string
        asn_lookup: Optional ASNLookup for IP-to-ASN resolution

    Returns:
        Dict with ip, asn, as_org, as_country fields
    """
    if asn_lookup is None:
        # No ASN data available - return minimal object
        return {
            "ip": ip,
            "asn": 0,
            "as_org": "Unknown",
            "as_country": "None",
        }

    record = asn_lookup.lookup(ip)
    if record is None:
        # IP not found in any range
        return {
            "ip": ip,
            "asn": 0,
            "as_org": "Unknown",
            "as_country": "None",
        }

    return {
        "ip": ip,
        "asn": record.asn,
        "as_org": record.org,
        "as_country": record.country,
    }


def _parse_gzipped_iptoasn(filepath: Path) -> list:
    """
    Parse a gzipped iptoasn TSV file.

    Args:
        filepath: Path to .tsv.gz file

    Returns:
        List of ASNRecord objects
    """
    from ..parse.iptoasn import ASNRecord

    records = []

    with gzip.open(filepath, "rt", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 5:
                continue

            try:
                start_ip = parts[0]
                end_ip = parts[1]
                asn = int(parts[2])
                country = parts[3]
                org = "\t".join(parts[4:])

                records.append(ASNRecord(
                    start_ip=start_ip,
                    end_ip=end_ip,
                    asn=asn,
                    country=country,
                    org=org,
                ))
            except ValueError:
                continue

    return records
