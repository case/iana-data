"""Parser for IANA RDAP Bootstrap JSON file."""

import json
from pathlib import Path


def parse_rdap_json(filepath: Path) -> dict:
    """
    Parse the RDAP Bootstrap JSON file.

    Args:
        filepath: Path to the RDAP JSON file

    Returns:
        Dict with analysis results:
        - total_tlds: Total number of TLDs in RDAP bootstrap
        - unique_servers: Count of unique RDAP servers
        - servers: List of unique RDAP server URLs
    """
    content = filepath.read_text()
    data = json.loads(content)

    total_tlds = 0
    unique_servers = set()

    # Process each service entry
    for service in data["services"]:
        tlds = service[0]
        servers = service[1]

        total_tlds += len(tlds)
        unique_servers.update(servers)

    return {
        "total_tlds": total_tlds,
        "unique_servers": len(unique_servers),
        "servers": sorted(unique_servers),
    }
