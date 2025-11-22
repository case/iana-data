#!/usr/bin/env python3
"""Analyze tlds.json file size breakdown by field."""

import json
from pathlib import Path


def analyze_tlds_json() -> None:
    """Analyze and print field size breakdown for tlds.json."""
    tlds_path = Path("data/generated/tlds.json")

    if not tlds_path.exists():
        print(f"Error: {tlds_path} not found. Run 'make build' first.")
        return

    data = json.loads(tlds_path.read_text())
    total_size = len(tlds_path.read_bytes())

    print(f"File: {tlds_path}")
    print(f"Total size: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
    print()

    # Analyze top-level fields
    print("=== Top-level fields ===")
    for key, value in data.items():
        size = len(json.dumps(value, ensure_ascii=False))
        print(f"  {key}: {size:,} bytes ({size/1024:.1f} KB)")

    # Analyze per-TLD fields
    print()
    print("=== Per-TLD field totals ===")
    field_sizes: dict[str, int] = {}
    for tld in data["tlds"]:
        for key, value in tld.items():
            size = len(json.dumps(value, ensure_ascii=False))
            field_sizes[key] = field_sizes.get(key, 0) + size

    # Sort by size descending
    sorted_fields = sorted(field_sizes.items(), key=lambda x: -x[1])
    total_tld_data = sum(field_sizes.values())
    for key, size in sorted_fields:
        pct = size / total_tld_data * 100
        print(f"  {key}: {size:,} bytes ({size/1024:.1f} KB) - {pct:.1f}%")

    print()
    print(f"  Total TLD data: {total_tld_data:,} bytes ({total_tld_data/1024/1024:.2f} MB)")

    # Analyze annotations sub-fields
    print()
    print("=== Annotations breakdown ===")
    ann_fields: dict[str, int] = {}
    for tld in data["tlds"]:
        if "annotations" in tld:
            for key, value in tld["annotations"].items():
                size = len(json.dumps(value, ensure_ascii=False))
                ann_fields[key] = ann_fields.get(key, 0) + size

    for key, size in sorted(ann_fields.items(), key=lambda x: -x[1]):
        print(f"  {key}: {size:,} bytes ({size/1024:.1f} KB)")

    # Analyze orgs sub-fields
    print()
    print("=== Orgs breakdown ===")
    orgs_fields: dict[str, int] = {}
    for tld in data["tlds"]:
        if "orgs" in tld:
            for key, value in tld["orgs"].items():
                size = len(json.dumps(value, ensure_ascii=False))
                orgs_fields[key] = orgs_fields.get(key, 0) + size

    for key, size in sorted(orgs_fields.items(), key=lambda x: -x[1]):
        print(f"  {key}: {size:,} bytes ({size/1024:.1f} KB)")

    # Stats
    print()
    print("=== Stats ===")
    total_tlds = len(data["tlds"])
    with_rdap = sum(1 for t in data["tlds"] if "rdap_server" in t)
    with_alias = sum(1 for t in data["tlds"] if t.get("orgs", {}).get("tld_manager_alias"))

    print(f"  Total TLDs: {total_tlds}")
    print(f"  With rdap_server: {with_rdap}")
    print(f"  With tld_manager_alias: {with_alias}")


if __name__ == "__main__":
    analyze_tlds_json()
