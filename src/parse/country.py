"""Country name lookup for ccTLDs using pycountry."""

import pycountry

from ..config import CCTLD_OVERRIDES


def get_country_name(cctld: str) -> str | None:
    """
    Get the country name for a ccTLD.

    Args:
        cctld: Two-letter country code TLD (e.g., 'us', 'gb', 'de')

    Returns:
        Country name or None if not found
    """
    cctld_lower = cctld.lower()

    # Check overrides first
    if cctld_lower in CCTLD_OVERRIDES:
        return CCTLD_OVERRIDES[cctld_lower]

    # Look up in pycountry
    country = pycountry.countries.get(alpha_2=cctld.upper())
    if country:
        return country.name

    return None


def is_cctld(tld: str) -> bool:
    """
    Check if a TLD is a country-code TLD.

    Args:
        tld: The TLD to check

    Returns:
        True if it's a ccTLD (2-letter, non-IDN)
    """
    return len(tld) == 2 and not tld.lower().startswith("xn")


def get_all_country_mappings(tlds: list[str]) -> dict[str, str]:
    """
    Get country name mappings for all ccTLDs in a list.

    Args:
        tlds: List of TLDs

    Returns:
        Dict mapping ccTLD -> country name
    """
    mappings = {}
    for tld in tlds:
        if is_cctld(tld):
            name = get_country_name(tld)
            if name:
                mappings[tld.lower()] = name
    return mappings
