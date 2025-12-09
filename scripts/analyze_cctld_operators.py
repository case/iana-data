#!/usr/bin/env python3
"""Analyze ccTLD operators to discover potential RDAP servers.

This script correlates data from multiple sources to identify ccTLDs that may have
undiscovered RDAP servers based on their backend operators:

1. TLD Manager aliases - ccTLDs managed by operators who also run gTLDs with RDAP
2. Tech contact aliases - ccTLDs with tech contacts matching known RDAP operators
3. AS Org aliases - ccTLDs using DNS infrastructure from known RDAP operators
4. Nameserver hostname patterns - ccTLDs sharing nameservers with gTLDs that have RDAP

The goal is to identify ccTLDs where we can guess RDAP URLs based on patterns from
related gTLDs operated by the same backend provider.
"""

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import MANUAL_DIR, TLDS_OUTPUT_FILE


@dataclass
class OperatorRDAPInfo:
    """Information about an operator's RDAP patterns."""

    name: str
    rdap_urls: set[str] = field(default_factory=set)
    gtlds: list[str] = field(default_factory=list)
    cctlds_with_rdap: list[str] = field(default_factory=list)
    cctlds_without_rdap: list[str] = field(default_factory=list)


def load_json_file(path: Path) -> dict:
    """Load and return JSON data from a file."""
    with open(path) as f:
        return json.load(f)


def load_tld_manager_aliases() -> dict[str, str]:
    """Load TLD manager aliases and return reverse lookup."""
    aliases_path = Path(MANUAL_DIR) / "tld-manager-aliases.json"
    if not aliases_path.exists():
        return {}

    data = load_json_file(aliases_path)
    reverse_lookup: dict[str, str] = {}
    for alias, entries in data.get("managerAliases", {}).items():
        for entry in entries:
            name = entry.get("name")
            if name:
                reverse_lookup[name] = alias
    return reverse_lookup


def load_as_org_aliases() -> dict[str, str]:
    """Load AS org aliases and return reverse lookup."""
    aliases_path = Path(MANUAL_DIR) / "as-org-aliases.json"
    if not aliases_path.exists():
        return {}

    data = load_json_file(aliases_path)
    reverse_lookup: dict[str, str] = {}
    for alias, entries in data.get("asOrgAliases", {}).items():
        for entry in entries:
            name = entry.get("name")
            if name:
                reverse_lookup[name] = alias
    return reverse_lookup


def extract_rdap_base_url(rdap_url: str) -> str:
    """Extract the base RDAP URL (without TLD-specific path)."""
    # e.g., "https://rdap.centralnic.com/bar/" -> "https://rdap.centralnic.com/"
    if not rdap_url:
        return ""
    parts = rdap_url.rstrip("/").rsplit("/", 1)
    if len(parts) > 1:
        return parts[0] + "/"
    return rdap_url


def get_as_org_aliases_for_tld(tld_entry: dict, as_org_aliases: dict[str, str]) -> set[str]:
    """Get all AS org aliases associated with a TLD's nameservers."""
    aliases = set()
    for ns in tld_entry.get("nameservers", []):
        if not isinstance(ns, dict):
            continue
        for ip_list in [ns.get("ipv4", []), ns.get("ipv6", [])]:
            for ip_obj in ip_list:
                if isinstance(ip_obj, dict):
                    as_org = ip_obj.get("as_org", "")
                    if as_org in as_org_aliases:
                        aliases.add(as_org_aliases[as_org])
    return aliases


def get_nameserver_base_hostnames(tld_entry: dict) -> set[str]:
    """Extract base nameserver hostnames (e.g., 'gtld-servers.net' from 'a.gtld-servers.net')."""
    hostnames = set()
    for ns in tld_entry.get("nameservers", []):
        if isinstance(ns, dict):
            hostname = ns.get("hostname", "")
            # Get the base domain (last two parts)
            parts = hostname.split(".")
            if len(parts) >= 2:
                base = ".".join(parts[-2:])
                hostnames.add(base)
    return hostnames


def print_section(title: str) -> None:
    """Print a section header."""
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def analyze_by_tld_manager(tlds_data: dict, tld_manager_aliases: dict[str, str]) -> dict[str, OperatorRDAPInfo]:
    """Analyze TLDs by their TLD manager aliases."""
    print_section("ANALYSIS BY TLD MANAGER")

    operators: dict[str, OperatorRDAPInfo] = defaultdict(lambda: OperatorRDAPInfo(name=""))

    for tld_entry in tlds_data.get("tlds", []):
        tld = tld_entry.get("tld", "")
        tld_type = tld_entry.get("type", "")
        delegated = tld_entry.get("delegated", False)
        rdap_server = tld_entry.get("rdap_server", "")

        if not delegated:
            continue

        # Get TLD manager and its alias
        orgs = tld_entry.get("orgs", {})
        tld_manager = orgs.get("tld_manager", "")

        # Check annotations for alias
        annotations = tld_entry.get("annotations", {})
        manager_alias = annotations.get("tld_manager_alias", "")

        # If no annotation, check if manager name itself is in aliases
        if not manager_alias and tld_manager in tld_manager_aliases:
            manager_alias = tld_manager_aliases[tld_manager]

        if not manager_alias:
            continue

        if operators[manager_alias].name == "":
            operators[manager_alias].name = manager_alias

        if rdap_server:
            operators[manager_alias].rdap_urls.add(extract_rdap_base_url(rdap_server))

        if tld_type == "gtld":
            operators[manager_alias].gtlds.append(tld)
        elif tld_type == "cctld":
            if rdap_server:
                operators[manager_alias].cctlds_with_rdap.append(tld)
            else:
                operators[manager_alias].cctlds_without_rdap.append(tld)

    # Print results
    print("\nOperators with both gTLDs (with RDAP) and ccTLDs (without RDAP):")
    print("-" * 80)

    candidates = []
    for alias, info in sorted(operators.items()):
        if info.gtlds and info.cctlds_without_rdap and info.rdap_urls:
            candidates.append((alias, info))

    if not candidates:
        print("  None found")
    else:
        for alias, info in candidates:
            print(f"\n  {alias}:")
            print(f"    RDAP URLs: {', '.join(sorted(info.rdap_urls))}")
            print(f"    gTLDs ({len(info.gtlds)}): {', '.join(sorted(info.gtlds)[:10])}")
            if len(info.gtlds) > 10:
                print(f"      ... and {len(info.gtlds) - 10} more")
            print(f"    ccTLDs without RDAP ({len(info.cctlds_without_rdap)}): {', '.join(sorted(info.cctlds_without_rdap))}")

    return dict(operators)


def analyze_by_tech_contact(tlds_data: dict, tld_manager_aliases: dict[str, str]) -> dict[str, OperatorRDAPInfo]:
    """Analyze TLDs by their tech contact."""
    print_section("ANALYSIS BY TECH CONTACT")

    operators: dict[str, OperatorRDAPInfo] = defaultdict(lambda: OperatorRDAPInfo(name=""))

    for tld_entry in tlds_data.get("tlds", []):
        tld = tld_entry.get("tld", "")
        tld_type = tld_entry.get("type", "")
        delegated = tld_entry.get("delegated", False)
        rdap_server = tld_entry.get("rdap_server", "")

        if not delegated:
            continue

        # Get tech contact
        orgs = tld_entry.get("orgs", {})
        tech = orgs.get("tech", "")

        if not tech:
            continue

        # Check if tech contact matches any known alias
        tech_alias = tld_manager_aliases.get(tech, "")

        # Also check if tech contact contains known operator names
        tech_lower = tech.lower()
        if not tech_alias:
            if "centralnic" in tech_lower:
                tech_alias = "CentralNic"
            elif "afilias" in tech_lower or "identity digital" in tech_lower:
                tech_alias = "Identity Digital"
            elif "verisign" in tech_lower:
                tech_alias = "VeriSign"

        if not tech_alias:
            continue

        if operators[tech_alias].name == "":
            operators[tech_alias].name = tech_alias

        if rdap_server:
            operators[tech_alias].rdap_urls.add(extract_rdap_base_url(rdap_server))

        if tld_type == "gtld":
            operators[tech_alias].gtlds.append(tld)
        elif tld_type == "cctld":
            if rdap_server:
                operators[tech_alias].cctlds_with_rdap.append(tld)
            else:
                operators[tech_alias].cctlds_without_rdap.append(tld)

    # Print results
    print("\nOperators (by tech contact) with ccTLDs without RDAP:")
    print("-" * 80)

    candidates = []
    for alias, info in sorted(operators.items()):
        if info.cctlds_without_rdap and info.rdap_urls:
            candidates.append((alias, info))

    if not candidates:
        print("  None found")
    else:
        for alias, info in candidates:
            print(f"\n  {alias}:")
            print(f"    RDAP URLs: {', '.join(sorted(info.rdap_urls))}")
            if info.cctlds_with_rdap:
                print(f"    ccTLDs with RDAP: {', '.join(sorted(info.cctlds_with_rdap))}")
            print(f"    ccTLDs without RDAP: {', '.join(sorted(info.cctlds_without_rdap))}")

    return dict(operators)


def analyze_by_as_org(tlds_data: dict, as_org_aliases: dict[str, str]) -> dict[str, OperatorRDAPInfo]:
    """Analyze TLDs by their nameserver AS organizations."""
    print_section("ANALYSIS BY NAMESERVER AS ORG")

    operators: dict[str, OperatorRDAPInfo] = defaultdict(lambda: OperatorRDAPInfo(name=""))

    for tld_entry in tlds_data.get("tlds", []):
        tld = tld_entry.get("tld", "")
        tld_type = tld_entry.get("type", "")
        delegated = tld_entry.get("delegated", False)
        rdap_server = tld_entry.get("rdap_server", "")

        if not delegated:
            continue

        # Get AS org aliases for this TLD
        as_aliases = get_as_org_aliases_for_tld(tld_entry, as_org_aliases)

        for alias in as_aliases:
            if operators[alias].name == "":
                operators[alias].name = alias

            if rdap_server:
                operators[alias].rdap_urls.add(extract_rdap_base_url(rdap_server))

            if tld_type == "gtld":
                if tld not in operators[alias].gtlds:
                    operators[alias].gtlds.append(tld)
            elif tld_type == "cctld":
                if rdap_server:
                    if tld not in operators[alias].cctlds_with_rdap:
                        operators[alias].cctlds_with_rdap.append(tld)
                else:
                    if tld not in operators[alias].cctlds_without_rdap:
                        operators[alias].cctlds_without_rdap.append(tld)

    # Print results - focus on operators with RDAP patterns
    print("\nDNS operators with ccTLDs without RDAP (and known RDAP URLs from other TLDs):")
    print("-" * 80)

    # Filter to operators that provide DNS for gTLDs with RDAP
    candidates = []
    for alias, info in sorted(operators.items()):
        if info.cctlds_without_rdap and info.rdap_urls:
            candidates.append((alias, info))

    if not candidates:
        print("  None found")
    else:
        for alias, info in candidates:
            print(f"\n  {alias}:")
            print(f"    RDAP URLs observed: {', '.join(sorted(info.rdap_urls)[:5])}")
            if len(info.rdap_urls) > 5:
                print(f"      ... and {len(info.rdap_urls) - 5} more")
            print(f"    gTLDs using this DNS ({len(info.gtlds)}): {', '.join(sorted(info.gtlds)[:8])}")
            if len(info.gtlds) > 8:
                print(f"      ... and {len(info.gtlds) - 8} more")
            print(f"    ccTLDs without RDAP ({len(info.cctlds_without_rdap)}): {', '.join(sorted(info.cctlds_without_rdap))}")

    return dict(operators)


def analyze_by_nameserver_pattern(tlds_data: dict) -> None:
    """Analyze TLDs by shared nameserver hostname patterns."""
    print_section("ANALYSIS BY NAMESERVER HOSTNAME PATTERNS")

    # Map base nameserver hostnames to TLDs and their RDAP status
    ns_to_tlds: dict[str, dict] = defaultdict(lambda: {"gtlds_with_rdap": [], "cctlds_with_rdap": [], "cctlds_without_rdap": [], "rdap_urls": set()})

    for tld_entry in tlds_data.get("tlds", []):
        tld = tld_entry.get("tld", "")
        tld_type = tld_entry.get("type", "")
        delegated = tld_entry.get("delegated", False)
        rdap_server = tld_entry.get("rdap_server", "")

        if not delegated:
            continue

        base_hostnames = get_nameserver_base_hostnames(tld_entry)

        for hostname in base_hostnames:
            if rdap_server:
                ns_to_tlds[hostname]["rdap_urls"].add(extract_rdap_base_url(rdap_server))

            if tld_type == "gtld":
                if rdap_server:
                    ns_to_tlds[hostname]["gtlds_with_rdap"].append(tld)
            elif tld_type == "cctld":
                if rdap_server:
                    ns_to_tlds[hostname]["cctlds_with_rdap"].append(tld)
                else:
                    ns_to_tlds[hostname]["cctlds_without_rdap"].append(tld)

    # Find nameserver patterns with both RDAP TLDs and non-RDAP ccTLDs
    print("\nNameserver patterns with ccTLDs that might have undiscovered RDAP:")
    print("-" * 80)

    candidates = []
    for hostname, info in sorted(ns_to_tlds.items()):
        if info["cctlds_without_rdap"] and info["rdap_urls"]:
            # Prioritize those with gTLDs (more likely to share RDAP infrastructure)
            candidates.append((hostname, info))

    # Sort by number of ccTLDs without RDAP
    candidates.sort(key=lambda x: len(x[1]["cctlds_without_rdap"]), reverse=True)

    if not candidates:
        print("  None found")
    else:
        for hostname, info in candidates[:15]:
            print(f"\n  {hostname}:")
            if info["rdap_urls"]:
                print(f"    RDAP URLs: {', '.join(sorted(info['rdap_urls'])[:3])}")
            if info["gtlds_with_rdap"]:
                print(f"    gTLDs with RDAP: {', '.join(sorted(info['gtlds_with_rdap'])[:5])}")
            if info["cctlds_with_rdap"]:
                print(f"    ccTLDs with RDAP: {', '.join(sorted(info['cctlds_with_rdap']))}")
            print(f"    ccTLDs without RDAP: {', '.join(sorted(info['cctlds_without_rdap']))}")


def generate_rdap_probe_candidates(tlds_data: dict, tld_manager_aliases: dict[str, str], as_org_aliases: dict[str, str]) -> None:
    """Generate a list of RDAP URLs to probe for ccTLDs."""
    print_section("RDAP PROBE CANDIDATES")

    # Collect all evidence for each ccTLD
    cctld_evidence: dict[str, dict] = defaultdict(lambda: {"rdap_urls": set(), "reasons": []})

    for tld_entry in tlds_data.get("tlds", []):
        tld = tld_entry.get("tld", "")
        tld_type = tld_entry.get("type", "")
        delegated = tld_entry.get("delegated", False)
        rdap_server = tld_entry.get("rdap_server", "")

        if not delegated or tld_type != "cctld" or rdap_server:
            continue

        # Check tech contact
        orgs = tld_entry.get("orgs", {})
        tech = orgs.get("tech", "")
        if tech:
            tech_lower = tech.lower()
            if "centralnic" in tech_lower:
                cctld_evidence[tld]["rdap_urls"].add("https://rdap.centralnic.com/")
                cctld_evidence[tld]["reasons"].append(f"Tech contact: {tech}")

        # Check AS org aliases
        as_aliases = get_as_org_aliases_for_tld(tld_entry, as_org_aliases)
        if "CentralNic" in as_aliases:
            cctld_evidence[tld]["rdap_urls"].add("https://rdap.centralnic.com/")
            cctld_evidence[tld]["reasons"].append("DNS on CentralNic AS")
        if "Identity Digital" in as_aliases:
            cctld_evidence[tld]["rdap_urls"].add("https://rdap.identitydigital.services/rdap/")
            cctld_evidence[tld]["reasons"].append("DNS on Identity Digital AS")

    # Print candidates
    print("\nccTLDs with potential RDAP URLs to probe:")
    print("-" * 80)

    if not cctld_evidence:
        print("  None found")
    else:
        for tld, evidence in sorted(cctld_evidence.items()):
            print(f"\n  .{tld}:")
            for url in sorted(evidence["rdap_urls"]):
                print(f"    Probe: {url}{tld}/domain/nic.{tld}")
            print(f"    Reasons: {'; '.join(evidence['reasons'])}")


def main() -> None:
    """Run the ccTLD operator analysis."""
    tlds_path = Path(TLDS_OUTPUT_FILE)

    if not tlds_path.exists():
        print(f"Error: {tlds_path} not found")
        print("Run 'make build' first to generate the tlds.json file.")
        return

    print(f"Loading TLD data from {tlds_path}...")
    tlds_data = load_json_file(tlds_path)

    print("Loading alias mappings...")
    tld_manager_aliases = load_tld_manager_aliases()
    as_org_aliases = load_as_org_aliases()

    print(f"  TLD manager aliases: {len(tld_manager_aliases)} names -> canonical aliases")
    print(f"  AS org aliases: {len(as_org_aliases)} names -> canonical aliases")

    # Count TLDs
    tlds = tlds_data.get("tlds", [])
    delegated_cctlds = [t for t in tlds if t.get("delegated") and t.get("type") == "cctld"]
    cctlds_with_rdap = [t for t in delegated_cctlds if t.get("rdap_server")]
    cctlds_without_rdap = [t for t in delegated_cctlds if not t.get("rdap_server")]

    print_section("SUMMARY")
    print(f"Delegated ccTLDs: {len(delegated_cctlds)}")
    print(f"  With RDAP: {len(cctlds_with_rdap)}")
    print(f"  Without RDAP: {len(cctlds_without_rdap)}")

    # Run analyses
    analyze_by_tld_manager(tlds_data, tld_manager_aliases)
    analyze_by_tech_contact(tlds_data, tld_manager_aliases)
    analyze_by_as_org(tlds_data, as_org_aliases)
    analyze_by_nameserver_pattern(tlds_data)
    generate_rdap_probe_candidates(tlds_data, tld_manager_aliases, as_org_aliases)

    print()
    print("=" * 80)
    print("Analysis complete.")
    print("=" * 80)


if __name__ == "__main__":
    main()
