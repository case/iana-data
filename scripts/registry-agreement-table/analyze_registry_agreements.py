#!/usr/bin/env python3
"""Analyze ICANN Registry Agreement Table CSV.

Provides insights into the registry agreement data including:
- Total TLDs and status breakdown
- Agreement types distribution
- Top operators by TLD count
- IDN TLDs with translations
- Agreement date ranges
"""

import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import SOURCE_DIR, SOURCE_FILES


def parse_agreement_types(agreement_type: str) -> list[str]:
    """Parse comma-separated agreement types into individual types."""
    if not agreement_type:
        return []
    # Split by comma and strip whitespace
    return [t.strip() for t in agreement_type.split(",")]


def parse_date(date_str: str) -> datetime | None:
    """Parse date string like '26 Feb 2015' to datetime."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%d %b %Y")
    except ValueError:
        return None


def main() -> int:
    """Analyze the registry agreement CSV."""
    csv_path = Path(SOURCE_DIR) / SOURCE_FILES["REGISTRY_AGREEMENT_TABLE"]

    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        print("Run the download script first.")
        return 1

    # Read and parse CSV
    rows = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"ICANN Registry Agreement Table Analysis")
    print(f"=" * 50)
    print(f"\nTotal TLDs: {len(rows)}")

    # Status breakdown
    status_counts = Counter(row["Agreement Status"] for row in rows)
    print(f"\n--- Agreement Status ---")
    for status, count in status_counts.most_common():
        pct = count / len(rows) * 100
        print(f"  {status:15s}: {count:4d} ({pct:5.1f}%)")

    # Agreement types breakdown
    type_counts: Counter = Counter()
    for row in rows:
        for t in parse_agreement_types(row["Agreement Type"]):
            type_counts[t] += 1

    print(f"\n--- Agreement Types ---")
    for agreement_type, count in type_counts.most_common():
        pct = count / len(rows) * 100
        print(f"  {agreement_type:35s}: {count:4d} ({pct:5.1f}%)")

    # Brand vs Non-Brand
    brand_count = sum(1 for row in rows if "Brand (Spec 13)" in row["Agreement Type"])
    community_count = sum(1 for row in rows if "Community (Spec 12)" in row["Agreement Type"])
    print(f"\n--- Special Categories ---")
    print(f"  Brand TLDs (Spec 13):     {brand_count:4d} ({brand_count/len(rows)*100:5.1f}%)")
    print(f"  Community TLDs (Spec 12): {community_count:4d} ({community_count/len(rows)*100:5.1f}%)")

    # Top operators
    operator_counts = Counter(row["Operator"] for row in rows if row["Operator"])
    print(f"\n--- Top 15 Operators by TLD Count ---")
    for operator, count in operator_counts.most_common(15):
        # Truncate long names
        display_name = operator[:45] + "..." if len(operator) > 45 else operator
        print(f"  {display_name:48s}: {count:3d}")

    # IDN TLDs (those with U-Label)
    idn_rows = [row for row in rows if row["U-Label"]]
    print(f"\n--- IDN TLDs ({len(idn_rows)} total) ---")
    for row in idn_rows[:20]:  # Show first 20
        tld = row["Top Level Domain"]
        ulabel = row["U-Label"]
        translation = row["Translation"] or ""
        status = row["Agreement Status"]
        print(f"  {tld:25s} → {ulabel:15s} {translation:20s} [{status}]")
    if len(idn_rows) > 20:
        print(f"  ... and {len(idn_rows) - 20} more")

    # Date analysis
    dates = [parse_date(row["Agreement Date"]) for row in rows]
    valid_dates = [d for d in dates if d]
    if valid_dates:
        earliest = min(valid_dates)
        latest = max(valid_dates)
        print(f"\n--- Agreement Date Range ---")
        print(f"  Earliest: {earliest.strftime('%d %b %Y')}")
        print(f"  Latest:   {latest.strftime('%d %b %Y')}")

        # Agreements by year
        year_counts = Counter(d.year for d in valid_dates)
        print(f"\n--- Agreements by Year ---")
        for year in sorted(year_counts.keys()):
            count = year_counts[year]
            bar = "█" * (count // 20)
            print(f"  {year}: {count:4d} {bar}")

    # Active TLDs only stats
    active_rows = [row for row in rows if row["Agreement Status"] == "active"]
    print(f"\n--- Active TLDs Summary ---")
    print(f"  Total active: {len(active_rows)}")

    active_operators = Counter(row["Operator"] for row in active_rows if row["Operator"])
    print(f"  Unique operators: {len(active_operators)}")

    # Show terminated TLDs
    terminated_rows = [row for row in rows if row["Agreement Status"] == "terminated"]
    if terminated_rows:
        print(f"\n--- Sample Terminated TLDs ({len(terminated_rows)} total) ---")
        for row in terminated_rows[:10]:
            tld = row["Top Level Domain"]
            operator = row["Operator"][:30] + "..." if len(row["Operator"]) > 30 else row["Operator"]
            print(f"  .{tld:15s} ({operator})")
        if len(terminated_rows) > 10:
            print(f"  ... and {len(terminated_rows) - 10} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
