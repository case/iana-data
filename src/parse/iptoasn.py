"""Parser for iptoasn TSV data files."""

import bisect
import ipaddress
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ASNRecord:
    """A single ASN record from iptoasn data."""

    start_ip: str
    end_ip: str
    asn: int
    country: str
    org: str


def parse_iptoasn_tsv(filepath: Path) -> list[ASNRecord]:
    """
    Parse an iptoasn TSV file into ASNRecord objects.

    The TSV format is: start_ip<TAB>end_ip<TAB>asn<TAB>country<TAB>org
    Both IPv4 and IPv6 records may be present in the same file.

    Args:
        filepath: Path to the TSV file (can be plain text or will be
                  decompressed if .gz extension)

    Returns:
        List of ASNRecord objects
    """
    records: list[ASNRecord] = []

    with open(filepath, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 5:
                logger.warning("Malformed line %d: expected 5 fields, got %d", line_num, len(parts))
                continue

            try:
                start_ip = parts[0]
                end_ip = parts[1]
                asn = int(parts[2])
                country = parts[3]
                # Org may contain tabs, so join remaining parts
                org = "\t".join(parts[4:])

                records.append(ASNRecord(
                    start_ip=start_ip,
                    end_ip=end_ip,
                    asn=asn,
                    country=country,
                    org=org,
                ))
            except ValueError as e:
                logger.warning("Error parsing line %d: %s", line_num, e)
                continue

    return records


class ASNLookup:
    """
    Efficient IP-to-ASN lookup using binary search.

    Maintains separate sorted lists for IPv4 and IPv6 ranges,
    using binary search for O(log n) lookups.
    """

    def __init__(self, records: list[ASNRecord]):
        """
        Initialize lookup tables from ASN records.

        Args:
            records: List of ASNRecord objects from parse_iptoasn_tsv
        """
        # Separate IPv4 and IPv6 records
        ipv4_records: list[ASNRecord] = []
        ipv6_records: list[ASNRecord] = []

        for record in records:
            if ":" in record.start_ip:
                ipv6_records.append(record)
            else:
                ipv4_records.append(record)

        # Sort by start IP (as integer for proper ordering)
        self._ipv4_records = sorted(
            ipv4_records,
            key=lambda r: int(ipaddress.IPv4Address(r.start_ip))
        )
        self._ipv6_records = sorted(
            ipv6_records,
            key=lambda r: int(ipaddress.IPv6Address(r.start_ip))
        )

        # Pre-compute start IPs as integers for binary search
        self._ipv4_starts = [
            int(ipaddress.IPv4Address(r.start_ip)) for r in self._ipv4_records
        ]
        self._ipv6_starts = [
            int(ipaddress.IPv6Address(r.start_ip)) for r in self._ipv6_records
        ]

    @classmethod
    def from_file(cls, filepath: Path) -> "ASNLookup":
        """
        Create an ASNLookup from a TSV file.

        Args:
            filepath: Path to iptoasn TSV file

        Returns:
            ASNLookup instance
        """
        records = parse_iptoasn_tsv(filepath)
        return cls(records)

    def lookup(self, ip: str) -> ASNRecord | None:
        """
        Look up ASN information for an IP address.

        Uses binary search for O(log n) performance.

        Args:
            ip: IPv4 or IPv6 address string

        Returns:
            ASNRecord if IP is in a known range, None otherwise
        """
        if ":" in ip:
            return self._lookup_ipv6(ip)
        else:
            return self._lookup_ipv4(ip)

    def _lookup_ipv4(self, ip: str) -> ASNRecord | None:
        """Look up an IPv4 address."""
        try:
            ip_int = int(ipaddress.IPv4Address(ip))
        except ipaddress.AddressValueError:
            return None

        # Binary search to find the range that might contain this IP
        idx = bisect.bisect_right(self._ipv4_starts, ip_int) - 1

        if idx < 0:
            return None

        record = self._ipv4_records[idx]
        end_int = int(ipaddress.IPv4Address(record.end_ip))

        if ip_int <= end_int:
            return record

        return None

    def _lookup_ipv6(self, ip: str) -> ASNRecord | None:
        """Look up an IPv6 address."""
        try:
            ip_int = int(ipaddress.IPv6Address(ip))
        except ipaddress.AddressValueError:
            return None

        # Binary search to find the range that might contain this IP
        idx = bisect.bisect_right(self._ipv6_starts, ip_int) - 1

        if idx < 0:
            return None

        record = self._ipv6_records[idx]
        end_int = int(ipaddress.IPv6Address(record.end_ip))

        if ip_int <= end_int:
            return record

        return None
