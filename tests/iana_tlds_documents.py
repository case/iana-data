"""Builders for synthetic IANA TLD JSON documents, shared by parser and build tests."""

from typing import Any


def contact(organization: str | None) -> dict[str, Any]:
    return {
        "name": "Role",
        "organization": organization,
        "address": None,
        "phone": None,
        "fax": None,
        "last_updated": None,
    }


def domain(**overrides: Any) -> dict[str, Any]:
    """One valid active gTLD record; keyword arguments replace top-level keys."""
    record: dict[str, Any] = {
        "name": "example",
        "status": "active",
        "type": "generic",
        "script_code": "Latn",
        "annotations": {"delegation_round": "2012"},
        "manager": {
            "organization": "Manager Org",
            "address": None,
            "last_updated": None,
        },
        "contacts": {"admin": contact("Admin Org"), "tech": contact("Tech Org")},
        "nameservers": [
            {"name": "a.nic.example", "ipv4": ["192.0.2.1"], "ipv6": ["2001:db8::1"]}
        ],
        "ds_records": [
            {"key_tag": 1, "algorithm": 8, "digest_type": 2, "digest": "ab12"}
        ],
        "rdap_base_urls": ["https://rdap.example/"],
        "whois_server": "whois.nic.example",
        "registration_url": "https://nic.example",
        "events": {"delegation": "2014-01-02", "revocation": None},
        "last_updated": "2026-01-02",
    }
    record.update(overrides)
    return record


def not_delegated(status: str, **overrides: Any) -> dict[str, Any]:
    """One valid record with a ``retired``, ``eligible`` or ``reserved`` status."""
    record = domain(
        status=status,
        manager=None,
        contacts=None,
        nameservers=[],
        ds_records=[],
        rdap_base_urls=[],
        events={
            "delegation": None,
            "revocation": "2020-01-02" if status == "retired" else None,
        },
    )
    if status == "reserved":
        record["purpose"] = "Reserved for a special use"
    record.update(overrides)
    return record


def document(*domains: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": {
            "generated": "2026-11-10T18:19:02+00:00",
            "source": "https://www.iana.org/domains/root/db",
            "schema": "https://data.iana.org/TLD/v1/tlds-schema.json",
            "specversion": 1,
        },
        "domains": list(domains) if domains else [domain()],
    }
