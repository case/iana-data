#!/usr/bin/env python3
"""Analyze all nameserver IP addresses from tlds.json.

This script aggregates all IPs to understand:
- Total unique IPs (IPv4 vs IPv6)
- Distribution of IPs per TLD
- Preparation for ASN lookup analysis
"""

import json
from collections import Counter
from pathlib import Path


def main() -> None:
    """Analyze all nameserver IPs from tlds.json."""
    tlds_path = Path("data/generated/tlds.json")

    if not tlds_path.exists():
        print(f"Error: {tlds_path} not found. Run 'make build' first.")
        return

    data = json.loads(tlds_path.read_text())

    # Collect all IPs
    all_ipv4: list[str] = []
    all_ipv6: list[str] = []
    ips_per_tld: list[tuple[str, int]] = []

    for tld_entry in data["tlds"]:
        tld = tld_entry["tld"]
        if "nameservers" not in tld_entry:
            continue

        tld_ipv4 = []
        tld_ipv6 = []
        for ns in tld_entry["nameservers"]:
            tld_ipv4.extend(ns.get("ipv4", []))
            tld_ipv6.extend(ns.get("ipv6", []))

        all_ipv4.extend(tld_ipv4)
        all_ipv6.extend(tld_ipv6)
        ips_per_tld.append((tld, len(tld_ipv4) + len(tld_ipv6)))

    # === Summary Statistics ===
    print("=" * 60)
    print("IP ADDRESS SUMMARY")
    print("=" * 60)

    print(f"\nTotal IPv4 addresses (with duplicates): {len(all_ipv4):,}")
    print(f"Total IPv6 addresses (with duplicates): {len(all_ipv6):,}")
    print(f"Total IPs (with duplicates): {len(all_ipv4) + len(all_ipv6):,}")

    unique_ipv4 = set(all_ipv4)
    unique_ipv6 = set(all_ipv6)
    print(f"\nUnique IPv4 addresses: {len(unique_ipv4):,}")
    print(f"Unique IPv6 addresses: {len(unique_ipv6):,}")
    print(f"Total unique IPs: {len(unique_ipv4) + len(unique_ipv6):,}")

    # === IP Reuse Analysis ===
    print("\n" + "=" * 60)
    print("IP REUSE ANALYSIS")
    print("=" * 60)

    ipv4_counts = Counter(all_ipv4)
    ipv6_counts = Counter(all_ipv6)

    print("\nMost reused IPv4 addresses:")
    for ip, count in ipv4_counts.most_common(10):
        print(f"  {count:4d}x {ip}")

    print("\nMost reused IPv6 addresses:")
    for ip, count in ipv6_counts.most_common(10):
        print(f"  {count:4d}x {ip}")

    # === TLD Distribution ===
    print("\n" + "=" * 60)
    print("IPs PER TLD DISTRIBUTION")
    print("=" * 60)

    ips_per_tld.sort(key=lambda x: -x[1])

    print("\nTLDs with most IPs:")
    for tld, count in ips_per_tld[:15]:
        print(f"  {tld}: {count} IPs")

    tld_ip_counts = [c for _, c in ips_per_tld]
    print(f"\nTLDs with nameservers: {len(ips_per_tld):,}")
    print(f"Average IPs per TLD: {sum(tld_ip_counts) / len(tld_ip_counts):.1f}")
    print(f"Median IPs per TLD: {sorted(tld_ip_counts)[len(tld_ip_counts) // 2]}")
    print(f"Max IPs per TLD: {max(tld_ip_counts)}")
    print(f"Min IPs per TLD: {min(tld_ip_counts)}")

    # === /24 and /48 Prefix Analysis ===
    print("\n" + "=" * 60)
    print("IP PREFIX ANALYSIS (potential ASN grouping)")
    print("=" * 60)

    # Group IPv4 by /24 prefix
    ipv4_prefixes = Counter()
    for ip in unique_ipv4:
        parts = ip.split(".")
        prefix = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        ipv4_prefixes[prefix] += 1

    print(f"\nUnique /24 prefixes (IPv4): {len(ipv4_prefixes):,}")
    print("Most common /24 prefixes:")
    for prefix, count in ipv4_prefixes.most_common(10):
        print(f"  {count:4d} IPs in {prefix}")

    # Group IPv6 by /48 prefix (common allocation size)
    ipv6_prefixes = Counter()
    for ip in unique_ipv6:
        # Expand IPv6 to full form for prefix extraction
        try:
            import ipaddress
            addr = ipaddress.IPv6Address(ip)
            # Get first 48 bits (3 groups of 16 bits)
            exploded = addr.exploded
            parts = exploded.split(":")
            prefix = f"{parts[0]}:{parts[1]}:{parts[2]}::/48"
            ipv6_prefixes[prefix] += 1
        except Exception:
            pass

    print(f"\nUnique /48 prefixes (IPv6): {len(ipv6_prefixes):,}")
    print("Most common /48 prefixes:")
    for prefix, count in ipv6_prefixes.most_common(10):
        print(f"  {count:4d} IPs in {prefix}")

    # === Sample IPs for testing ===
    print("\n" + "=" * 60)
    print("SAMPLE IPs (for ASN lookup testing)")
    print("=" * 60)

    print("\nSample IPv4 addresses:")
    for ip in sorted(unique_ipv4)[:10]:
        print(f"  {ip}")

    print("\nSample IPv6 addresses:")
    for ip in sorted(unique_ipv6)[:10]:
        print(f"  {ip}")

    # === Output unique IPs for external lookup ===
    print("\n" + "=" * 60)
    print("UNIQUE IP EXPORT")
    print("=" * 60)

    output_dir = Path("local/analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    ipv4_file = output_dir / "unique_ipv4.txt"
    ipv6_file = output_dir / "unique_ipv6.txt"

    ipv4_file.write_text("\n".join(sorted(unique_ipv4)) + "\n")
    ipv6_file.write_text("\n".join(sorted(unique_ipv6)) + "\n")

    print(f"\nExported {len(unique_ipv4):,} unique IPv4 to {ipv4_file}")
    print(f"Exported {len(unique_ipv6):,} unique IPv6 to {ipv6_file}")


if __name__ == "__main__":
    main()
