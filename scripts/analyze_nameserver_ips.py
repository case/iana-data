#!/usr/bin/env python3
"""Analyze nameserver IP address data from TLD HTML pages.

This script scans all TLD pages to understand the IP address landscape:
- Count of IPv4 vs IPv6 addresses
- TLDs with/without nameservers
- Edge cases (multiple IPs per type, missing IPs, etc.)
- HTML structure variations
"""

import ipaddress
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from selectolax.parser import HTMLParser


@dataclass
class NameserverInfo:
    """Info about a single nameserver."""

    hostname: str
    ipv4_addresses: list[str] = field(default_factory=list)
    ipv6_addresses: list[str] = field(default_factory=list)
    raw_ip_text: str = ""


@dataclass
class TLDAnalysis:
    """Analysis results for a single TLD."""

    tld: str
    nameservers: list[NameserverInfo] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


def normalize_ipv6(addr: str) -> str:
    """Normalize IPv6 address to compressed form."""
    try:
        return str(ipaddress.IPv6Address(addr))
    except ipaddress.AddressValueError:
        return addr


def classify_ip(ip: str) -> str | None:
    """Classify an IP address as 'ipv4' or 'ipv6', or None if invalid."""
    ip = ip.strip()
    if not ip:
        return None
    try:
        ipaddress.IPv4Address(ip)
        return "ipv4"
    except ipaddress.AddressValueError:
        pass
    try:
        ipaddress.IPv6Address(ip)
        return "ipv6"
    except ipaddress.AddressValueError:
        pass
    return None


def parse_nameservers_with_ips(html: str) -> tuple[list[NameserverInfo], list[str]]:
    """Parse nameservers and their IP addresses from TLD HTML.

    Returns:
        Tuple of (nameserver_list, parse_errors)
    """
    tree = HTMLParser(html)
    nameservers: list[NameserverInfo] = []
    errors: list[str] = []

    for table in tree.css("table"):
        # Check if this looks like a nameserver table
        thead = table.css_first("thead")
        if not thead:
            continue

        header_text = thead.text().lower()
        if "host name" not in header_text and "ip address" not in header_text:
            continue

        # Found the nameserver table
        for row in table.css("tbody tr"):
            tds = row.css("td")
            if len(tds) < 2:
                if len(tds) == 1:
                    errors.append(f"Row with only 1 td: {tds[0].text().strip()}")
                continue

            hostname = tds[0].text().strip()
            if not hostname:
                continue

            # Get raw IP text and parse it
            ip_td = tds[1]
            raw_ip_html = ip_td.html or ""
            raw_ip_text = ip_td.text().strip()

            ns_info = NameserverInfo(hostname=hostname, raw_ip_text=raw_ip_text)

            # Split on <br> tags or newlines
            # The HTML often has <br></br> or <br><br> patterns
            ip_parts = re.split(r"<br\s*/?>(?:</br>)?|\n", raw_ip_html)

            for part in ip_parts:
                # Extract text content, removing any HTML tags
                ip_text = re.sub(r"<[^>]+>", "", part).strip()
                if not ip_text:
                    continue

                ip_type = classify_ip(ip_text)
                if ip_type == "ipv4":
                    ns_info.ipv4_addresses.append(ip_text)
                elif ip_type == "ipv6":
                    # Normalize IPv6
                    ns_info.ipv6_addresses.append(normalize_ipv6(ip_text))
                elif ip_text:
                    errors.append(f"Unrecognized IP format for {hostname}: '{ip_text}'")

            nameservers.append(ns_info)

        # Found and processed the nameserver table
        break

    return nameservers, errors


def analyze_tld_file(html_path: Path) -> TLDAnalysis:
    """Analyze a single TLD HTML file."""
    tld = html_path.stem
    html = html_path.read_text()

    nameservers, errors = parse_nameservers_with_ips(html)

    return TLDAnalysis(tld=tld, nameservers=nameservers, parse_errors=errors)


def main() -> None:
    """Run the analysis on all TLD pages."""
    tld_pages_dir = Path("data/source/tld-pages")

    if not tld_pages_dir.exists():
        print(f"Error: {tld_pages_dir} not found")
        return

    # Collect all HTML files
    html_files = sorted(tld_pages_dir.glob("**/*.html"))
    print(f"Found {len(html_files)} TLD HTML files")
    print()

    # Analyze each file
    analyses: list[TLDAnalysis] = []
    for html_path in html_files:
        analysis = analyze_tld_file(html_path)
        analyses.append(analysis)

    # === Summary Statistics ===
    print("=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)

    total_tlds = len(analyses)
    tlds_with_ns = [a for a in analyses if a.nameservers]
    tlds_without_ns = [a for a in analyses if not a.nameservers]

    print(f"Total TLDs: {total_tlds}")
    print(f"TLDs with nameservers: {len(tlds_with_ns)}")
    print(f"TLDs without nameservers: {len(tlds_without_ns)}")

    if tlds_without_ns:
        print(f"  Examples: {', '.join(a.tld for a in tlds_without_ns[:10])}")

    # Count nameservers and IPs
    total_nameservers = sum(len(a.nameservers) for a in analyses)
    total_ipv4 = sum(
        len(ns.ipv4_addresses) for a in analyses for ns in a.nameservers
    )
    total_ipv6 = sum(
        len(ns.ipv6_addresses) for a in analyses for ns in a.nameservers
    )

    print()
    print(f"Total nameserver entries: {total_nameservers}")
    print(f"Total IPv4 addresses: {total_ipv4}")
    print(f"Total IPv6 addresses: {total_ipv6}")
    print(f"Total IP addresses: {total_ipv4 + total_ipv6}")

    # Average per TLD
    if tlds_with_ns:
        avg_ns = total_nameservers / len(tlds_with_ns)
        print(f"Average nameservers per TLD (with NS): {avg_ns:.1f}")

    # === Edge Cases ===
    print()
    print("=" * 60)
    print("EDGE CASES")
    print("=" * 60)

    # Nameservers without any IPs
    ns_without_ips = []
    for a in analyses:
        for ns in a.nameservers:
            if not ns.ipv4_addresses and not ns.ipv6_addresses:
                ns_without_ips.append((a.tld, ns.hostname, ns.raw_ip_text))

    print(f"\nNameservers without any IP addresses: {len(ns_without_ips)}")
    if ns_without_ips:
        for tld, hostname, raw in ns_without_ips[:10]:
            print(f"  {tld}: {hostname} (raw: '{raw}')")
        if len(ns_without_ips) > 10:
            print(f"  ... and {len(ns_without_ips) - 10} more")

    # Nameservers with only IPv4
    ns_ipv4_only = []
    for a in analyses:
        for ns in a.nameservers:
            if ns.ipv4_addresses and not ns.ipv6_addresses:
                ns_ipv4_only.append((a.tld, ns.hostname))

    print(f"\nNameservers with IPv4 only (no IPv6): {len(ns_ipv4_only)}")
    if ns_ipv4_only:
        for tld, hostname in ns_ipv4_only[:5]:
            print(f"  {tld}: {hostname}")
        if len(ns_ipv4_only) > 5:
            print(f"  ... and {len(ns_ipv4_only) - 5} more")

    # Nameservers with only IPv6
    ns_ipv6_only = []
    for a in analyses:
        for ns in a.nameservers:
            if ns.ipv6_addresses and not ns.ipv4_addresses:
                ns_ipv6_only.append((a.tld, ns.hostname))

    print(f"\nNameservers with IPv6 only (no IPv4): {len(ns_ipv6_only)}")
    if ns_ipv6_only:
        for tld, hostname in ns_ipv6_only[:5]:
            print(f"  {tld}: {hostname}")
        if len(ns_ipv6_only) > 5:
            print(f"  ... and {len(ns_ipv6_only) - 5} more")

    # Nameservers with multiple IPs of same type
    ns_multi_ipv4 = []
    ns_multi_ipv6 = []
    for a in analyses:
        for ns in a.nameservers:
            if len(ns.ipv4_addresses) > 1:
                ns_multi_ipv4.append((a.tld, ns.hostname, ns.ipv4_addresses))
            if len(ns.ipv6_addresses) > 1:
                ns_multi_ipv6.append((a.tld, ns.hostname, ns.ipv6_addresses))

    print(f"\nNameservers with multiple IPv4 addresses: {len(ns_multi_ipv4)}")
    for tld, hostname, ips in ns_multi_ipv4[:5]:
        print(f"  {tld}: {hostname} -> {ips}")

    print(f"\nNameservers with multiple IPv6 addresses: {len(ns_multi_ipv6)}")
    for tld, hostname, ips in ns_multi_ipv6[:5]:
        print(f"  {tld}: {hostname} -> {ips}")

    # === Parse Errors ===
    print()
    print("=" * 60)
    print("PARSE ERRORS")
    print("=" * 60)

    all_errors = [(a.tld, err) for a in analyses for err in a.parse_errors]
    print(f"Total parse errors: {len(all_errors)}")
    for tld, err in all_errors[:20]:
        print(f"  {tld}: {err}")
    if len(all_errors) > 20:
        print(f"  ... and {len(all_errors) - 20} more")

    # === Unique Hostnames ===
    print()
    print("=" * 60)
    print("HOSTNAME ANALYSIS")
    print("=" * 60)

    all_hostnames = [ns.hostname for a in analyses for ns in a.nameservers]
    unique_hostnames = set(all_hostnames)
    hostname_counts = Counter(all_hostnames)

    print(f"Total hostname entries: {len(all_hostnames)}")
    print(f"Unique hostnames: {len(unique_hostnames)}")

    print("\nMost common nameserver hostnames:")
    for hostname, count in hostname_counts.most_common(15):
        print(f"  {count:4d}x {hostname}")

    # === Sample Output ===
    print()
    print("=" * 60)
    print("FIXTURE CANDIDATES")
    print("=" * 60)

    # 1. TLDs without nameservers (likely undelegated)
    print("\n1. TLDs WITHOUT NAMESERVERS (for undelegated fixture):")
    for a in tlds_without_ns[:5]:
        print(f"  {a.tld}")

    # 2. TLDs with IPv4-only nameservers
    print("\n2. TLDs WITH IPv4-ONLY NAMESERVERS:")
    ipv4_only_tlds = []
    for a in analyses:
        if a.nameservers and all(
            ns.ipv4_addresses and not ns.ipv6_addresses for ns in a.nameservers
        ):
            ipv4_only_tlds.append(a)
    for a in ipv4_only_tlds[:3]:
        print(f"  {a.tld}:")
        for ns in a.nameservers[:2]:
            print(f"    {ns.hostname} -> IPv4: {ns.ipv4_addresses}")
    print(f"  Total TLDs with all-IPv4-only nameservers: {len(ipv4_only_tlds)}")

    # 3. TLDs with IPv6-only nameservers
    print("\n3. TLDs WITH IPv6-ONLY NAMESERVERS:")
    ipv6_only_tlds = []
    for a in analyses:
        if a.nameservers and all(
            ns.ipv6_addresses and not ns.ipv4_addresses for ns in a.nameservers
        ):
            ipv6_only_tlds.append(a)
    for a in ipv6_only_tlds[:3]:
        print(f"  {a.tld}:")
        for ns in a.nameservers[:2]:
            print(f"    {ns.hostname} -> IPv6: {ns.ipv6_addresses}")
    print(f"  Total TLDs with all-IPv6-only nameservers: {len(ipv6_only_tlds)}")

    # 4. Nameservers with multiple IPv4 addresses (for fixture)
    print("\n4. NAMESERVERS WITH MULTIPLE IPv4 ADDRESSES:")
    if ns_multi_ipv4:
        for tld, hostname, ips in ns_multi_ipv4[:3]:
            print(f"  {tld}: {hostname}")
            print(f"    IPv4 addresses: {ips}")
    else:
        print("  None found")

    # 5. Nameservers with multiple IPv6 addresses (for fixture)
    print("\n5. NAMESERVERS WITH MULTIPLE IPv6 ADDRESSES:")
    if ns_multi_ipv6:
        for tld, hostname, ips in ns_multi_ipv6[:3]:
            print(f"  {tld}: {hostname}")
            print(f"    IPv6 addresses: {ips}")
    else:
        print("  None found")

    # 6. Standard examples (both IPv4 and IPv6)
    print("\n6. STANDARD EXAMPLES (both IPv4 and IPv6):")
    examples = ["vc", "com", "uk"]
    for tld_name in examples:
        analysis = next((a for a in analyses if a.tld == tld_name), None)
        if analysis:
            print(f"  {tld_name}:")
            for ns in analysis.nameservers[:2]:
                print(f"    {ns.hostname}")
                print(f"      IPv4: {ns.ipv4_addresses}")
                print(f"      IPv6: {ns.ipv6_addresses}")
            if len(analysis.nameservers) > 2:
                print(f"    ... and {len(analysis.nameservers) - 2} more nameservers")


if __name__ == "__main__":
    main()
