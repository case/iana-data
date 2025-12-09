#!/usr/bin/env python3
"""Analyze nameserver ASN data from tlds.json.

This script analyzes ASN (Autonomous System Number) data across all TLDs to understand:
- ASN concentration: Which ASNs host the most TLD nameservers?
- Single-ASN risk: TLDs with all nameservers on a single ASN
- Geographic distribution: Where is TLD infrastructure hosted?
- Diversity metrics: How diverse is each TLD's nameserver infrastructure?
"""

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import TLDS_OUTPUT_FILE


@dataclass
class ASNInfo:
    """Information about an ASN."""

    asn: int
    org: str
    country: str


@dataclass
class TLDASNProfile:
    """ASN profile for a single TLD."""

    tld: str
    tld_type: str
    delegated: bool
    unique_asns: set[int] = field(default_factory=set)
    asn_details: dict[int, ASNInfo] = field(default_factory=dict)
    ip_count: int = 0
    nameserver_count: int = 0


def load_tlds_json(path: Path) -> dict:
    """Load and return the tlds.json data."""
    with open(path) as f:
        return json.load(f)


def extract_asn_profiles(tlds_data: dict) -> list[TLDASNProfile]:
    """Extract ASN profiles from all TLDs."""
    profiles = []

    for tld_entry in tlds_data.get("tlds", []):
        profile = TLDASNProfile(
            tld=tld_entry.get("tld", ""),
            tld_type=tld_entry.get("type", "unknown"),
            delegated=tld_entry.get("delegated", False),
        )

        nameservers = tld_entry.get("nameservers", [])
        if not nameservers:
            profiles.append(profile)
            continue

        profile.nameserver_count = len(nameservers)

        for ns in nameservers:
            # Handle both old format (string) and new format (object)
            if isinstance(ns, str):
                continue

            # Process IPv4 and IPv6 addresses
            for ip_list in [ns.get("ipv4", []), ns.get("ipv6", [])]:
                for ip_obj in ip_list:
                    if not isinstance(ip_obj, dict):
                        continue

                    profile.ip_count += 1
                    asn = ip_obj.get("asn")
                    if asn is not None and asn > 0:  # Skip ASN 0 (not routed)
                        profile.unique_asns.add(asn)
                        if asn not in profile.asn_details:
                            profile.asn_details[asn] = ASNInfo(
                                asn=asn,
                                org=ip_obj.get("as_org", ""),
                                country=ip_obj.get("as_country", ""),
                            )

        profiles.append(profile)

    return profiles


def print_section(title: str) -> None:
    """Print a section header."""
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def analyze_concentration(profiles: list[TLDASNProfile]) -> None:
    """Analyze ASN concentration across TLDs."""
    print_section("ASN CONCENTRATION ANALYSIS")

    # Count TLDs per ASN
    asn_to_tlds: dict[int, list[str]] = defaultdict(list)
    asn_to_info: dict[int, ASNInfo] = {}

    for profile in profiles:
        for asn, info in profile.asn_details.items():
            asn_to_tlds[asn].append(profile.tld)
            asn_to_info[asn] = info

    # Sort by TLD count
    sorted_asns = sorted(asn_to_tlds.items(), key=lambda x: len(x[1]), reverse=True)

    print("\nTop 20 ASNs by TLD count:")
    print("-" * 70)
    print(f"{'Rank':<5} {'ASN':<10} {'TLDs':<6} {'Organization':<30} {'Country'}")
    print("-" * 70)

    for rank, (asn, tlds) in enumerate(sorted_asns[:20], 1):
        info = asn_to_info.get(asn, ASNInfo(asn, "", ""))
        org_display = info.org[:28] + ".." if len(info.org) > 30 else info.org
        print(f"{rank:<5} {asn:<10} {len(tlds):<6} {org_display:<30} {info.country}")

    # Summary stats
    total_asns = len(asn_to_tlds)
    top_10_coverage = sum(len(tlds) for _, tlds in sorted_asns[:10])
    total_tld_asn_pairs = sum(len(tlds) for tlds in asn_to_tlds.values())

    print()
    print(f"Total unique ASNs hosting TLD nameservers: {total_asns}")
    print(f"Top 10 ASNs cover {top_10_coverage} TLD associations ({100*top_10_coverage/total_tld_asn_pairs:.1f}% of all)")


def analyze_single_asn_risk(profiles: list[TLDASNProfile]) -> None:
    """Identify TLDs with all nameservers on a single ASN."""
    print_section("SINGLE-ASN RISK ANALYSIS")

    # Only consider delegated TLDs with nameservers
    delegated_with_ns = [p for p in profiles if p.delegated and p.ip_count > 0]

    single_asn_tlds = [p for p in delegated_with_ns if len(p.unique_asns) == 1]
    multi_asn_tlds = [p for p in delegated_with_ns if len(p.unique_asns) > 1]

    print(f"\nDelegated TLDs with nameserver IPs: {len(delegated_with_ns)}")
    print(f"TLDs with single ASN (potential risk): {len(single_asn_tlds)} ({100*len(single_asn_tlds)/len(delegated_with_ns):.1f}%)")
    print(f"TLDs with multiple ASNs: {len(multi_asn_tlds)} ({100*len(multi_asn_tlds)/len(delegated_with_ns):.1f}%)")

    # Group single-ASN TLDs by their ASN
    single_asn_groups: dict[int, list[TLDASNProfile]] = defaultdict(list)
    for profile in single_asn_tlds:
        asn = next(iter(profile.unique_asns))
        single_asn_groups[asn].append(profile)

    # Sort by count
    sorted_groups = sorted(single_asn_groups.items(), key=lambda x: len(x[1]), reverse=True)

    print("\nTop ASNs with single-ASN TLDs (highest risk concentration):")
    print("-" * 70)
    for asn, tld_profiles in sorted_groups[:10]:
        info = tld_profiles[0].asn_details.get(asn, ASNInfo(asn, "", ""))
        tld_list = ", ".join(p.tld for p in tld_profiles[:5])
        if len(tld_profiles) > 5:
            tld_list += f", ... (+{len(tld_profiles)-5} more)"
        print(f"  ASN {asn} ({info.org}, {info.country}): {len(tld_profiles)} TLDs")
        print(f"    Examples: {tld_list}")

    # Show some specific examples with details
    print("\nExample single-ASN TLDs (with nameserver counts):")
    for profile in single_asn_tlds[:10]:
        asn = next(iter(profile.unique_asns))
        info = profile.asn_details.get(asn, ASNInfo(asn, "", ""))
        print(f"  .{profile.tld} ({profile.tld_type}): {profile.nameserver_count} NS, {profile.ip_count} IPs, all on ASN {asn} ({info.org})")


def analyze_geographic_distribution(profiles: list[TLDASNProfile]) -> None:
    """Analyze geographic distribution of TLD infrastructure."""
    print_section("GEOGRAPHIC DISTRIBUTION")

    # Count IPs per country (weighted by occurrence)
    country_ip_count: Counter[str] = Counter()
    country_tld_count: dict[str, set[str]] = defaultdict(set)

    for profile in profiles:
        if not profile.delegated:
            continue
        for asn, info in profile.asn_details.items():
            country = info.country or "Unknown"
            country_ip_count[country] += 1  # Count ASN presence
            country_tld_count[country].add(profile.tld)

    total_country_refs = sum(country_ip_count.values())

    print("\nASN country distribution (by TLD-ASN associations):")
    print("-" * 50)
    print(f"{'Country':<12} {'ASN Refs':<10} {'%':<8} {'TLDs'}")
    print("-" * 50)

    for country, count in country_ip_count.most_common(15):
        pct = 100 * count / total_country_refs
        tld_count = len(country_tld_count[country])
        print(f"{country:<12} {count:<10} {pct:<8.1f} {tld_count}")

    # Analyze ccTLDs hosted outside their country
    print("\nccTLD infrastructure location analysis:")
    cctld_profiles = [p for p in profiles if p.tld_type == "cctld" and p.delegated and p.unique_asns]

    cctld_outside = []
    for profile in cctld_profiles:
        tld_country = profile.tld.upper()
        asn_countries = {info.country for info in profile.asn_details.values() if info.country}
        if asn_countries and tld_country not in asn_countries:
            cctld_outside.append((profile, asn_countries))

    print(f"  ccTLDs with ASN data: {len(cctld_profiles)}")
    print(f"  ccTLDs hosted entirely outside their country code: {len(cctld_outside)}")

    if cctld_outside:
        print("\n  Examples of ccTLDs hosted outside their country:")
        for profile, countries in cctld_outside[:15]:
            countries_str = ", ".join(sorted(countries))
            print(f"    .{profile.tld} -> {countries_str}")


def analyze_diversity_metrics(profiles: list[TLDASNProfile]) -> None:
    """Analyze diversity metrics for TLDs."""
    print_section("TLD DIVERSITY METRICS")

    delegated_with_asn = [p for p in profiles if p.delegated and p.unique_asns]

    if not delegated_with_asn:
        print("No delegated TLDs with ASN data found.")
        return

    # ASN diversity distribution
    asn_counts = [len(p.unique_asns) for p in delegated_with_asn]
    avg_asns = sum(asn_counts) / len(asn_counts)
    max_asns = max(asn_counts)
    min_asns = min(asn_counts)

    print(f"\nASN diversity per TLD:")
    print(f"  Average unique ASNs per TLD: {avg_asns:.2f}")
    print(f"  Minimum: {min_asns}")
    print(f"  Maximum: {max_asns}")

    # Distribution histogram
    asn_distribution = Counter(asn_counts)
    print("\n  Distribution:")
    for count in sorted(asn_distribution.keys()):
        bar = "█" * min(asn_distribution[count] // 10, 50)
        print(f"    {count} ASN(s): {asn_distribution[count]:4d} TLDs {bar}")

    # Most diverse TLDs
    most_diverse = sorted(delegated_with_asn, key=lambda p: len(p.unique_asns), reverse=True)
    print("\nMost diverse TLDs (most unique ASNs):")
    for profile in most_diverse[:10]:
        countries = {info.country for info in profile.asn_details.values()}
        print(f"  .{profile.tld}: {len(profile.unique_asns)} ASNs across {len(countries)} countries")

    # Compare gTLD vs ccTLD diversity
    gtld_profiles = [p for p in delegated_with_asn if p.tld_type == "gtld"]
    cctld_profiles = [p for p in delegated_with_asn if p.tld_type == "cctld"]

    if gtld_profiles and cctld_profiles:
        gtld_avg = sum(len(p.unique_asns) for p in gtld_profiles) / len(gtld_profiles)
        cctld_avg = sum(len(p.unique_asns) for p in cctld_profiles) / len(cctld_profiles)

        print(f"\ngTLD vs ccTLD ASN diversity:")
        print(f"  gTLDs ({len(gtld_profiles)} total): {gtld_avg:.2f} avg ASNs per TLD")
        print(f"  ccTLDs ({len(cctld_profiles)} total): {cctld_avg:.2f} avg ASNs per TLD")


def analyze_ipv4_vs_ipv6(profiles: list[TLDASNProfile]) -> None:
    """Compare IPv4 vs IPv6 ASN patterns."""
    print_section("IPv4 vs IPv6 ASN ANALYSIS")

    # This would require re-processing with IP type distinction
    # For now, just note it as future enhancement
    print("\nNote: Detailed IPv4 vs IPv6 ASN comparison would require")
    print("tracking ASNs separately by IP version. This could reveal:")
    print("  - TLDs with different ASNs for IPv4 vs IPv6")
    print("  - IPv6-only or IPv4-only nameserver deployments")
    print("  - ASN differences between protocol versions")


def main() -> None:
    """Run the ASN analysis."""
    tlds_path = Path(TLDS_OUTPUT_FILE)

    if not tlds_path.exists():
        print(f"Error: {tlds_path} not found")
        print("Run 'make build' first to generate the tlds.json file.")
        return

    print(f"Loading TLD data from {tlds_path}...")
    tlds_data = load_tlds_json(tlds_path)

    print(f"Extracting ASN profiles...")
    profiles = extract_asn_profiles(tlds_data)

    # Summary
    delegated_count = sum(1 for p in profiles if p.delegated)
    with_asn_count = sum(1 for p in profiles if p.unique_asns)
    total_ips = sum(p.ip_count for p in profiles)

    print_section("SUMMARY")
    print(f"Total TLDs: {len(profiles)}")
    print(f"Delegated TLDs: {delegated_count}")
    print(f"TLDs with ASN data: {with_asn_count}")
    print(f"Total IP addresses analyzed: {total_ips}")

    # Run all analyses
    analyze_concentration(profiles)
    analyze_single_asn_risk(profiles)
    analyze_geographic_distribution(profiles)
    analyze_diversity_metrics(profiles)
    analyze_ipv4_vs_ipv6(profiles)

    print()
    print("=" * 70)
    print("Analysis complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
