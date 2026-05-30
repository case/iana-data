"""Build data/generated/places.json.

Countries are derived mechanically from ccTLDs (pycountry + CCTLD_OVERRIDES);
subdivisions, cities, and supranational regions come from the editorial
data/manual/places.json (keyed by slug, carrying their own tlds[]). Dependent
territories and the ISO special-status codes enrich the country records.

data/manual/country-coordinates.json overlays a lat/lon + info_link onto derived
countries that have no boundary polygon (e.g. Bouvet), so consumers can pin them.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pycountry

from ..parse.country import get_country_name, is_cctld
from ..utilities.content_changed import write_json_if_changed

logger = logging.getLogger(__name__)

_DESCRIPTION = (
    "Places associated with TLDs in the IANA root zone (countries, dependent "
    "territories, subdivisions, cities, and supranational regions), each with a "
    "reverse index of its TLDs. Country slugs are ISO 3166-1 alpha-2."
)

_SOURCES = [
    "pycountry (ISO 3166-1 / 3166-2)",
    "data/manual/places.json (editorial)",
    "data/manual/dependent-territories.json (editorial; ISO 3166-1)",
    "data/manual/country-coordinates.json (editorial; point overlay)",
]

# Delegated ccTLDs that are not ordinary sovereign countries. ISO 3166-1
# vocabulary: (iso_designation, parent place slug).
_SPECIAL: dict[str, tuple[str, str | None]] = {
    "ac": ("exceptionally_reserved", "sh"),
    "su": ("transitionally_reserved", None),
    "aq": ("special_area", None),
}


def _ordered_place(record: dict) -> dict:
    """Return ``record`` with its fields alphabetized, for one consistent order
    across all record types (the byte-equality writer makes field order matter)."""
    return {key: record[key] for key in sorted(record)}


def build_places_json(
    tlds: list[dict],
    manual_places: dict[str, dict],
    dependent_territories: dict[str, list[str]],
    country_coordinates: dict[str, dict],
    output_path: Path,
) -> tuple[bool, str]:
    """Combine derived country records with editorial places and write the file.

    Args:
        tlds: The built TLD entries (source of country reverse-index membership).
        manual_places: Editorial subdivisions/cities/supranational, keyed by slug.
        dependent_territories: Map of sovereign slug to its list of dependent
            territory slugs (e.g. ``{"gb": ["ai", "bm", ...], ...}``).
        country_coordinates: Point overlay keyed by slug (info_link + fetched
            coordinates) for polygon-less territories.
        output_path: Destination for the generated artifact.

    Returns:
        The ``(changed, status)`` tuple from ``write_json_if_changed``.
    """
    claimed = {tld for rec in manual_places.values() for tld in rec["tlds"]}
    countries = _build_countries(tlds, claimed, dependent_territories)
    _overlay_country_coordinates(countries, country_coordinates)

    records = [
        _ordered_place(rec)
        for rec in (*countries.values(), *_manual_records(manual_places))
    ]
    records.sort(key=lambda r: r["slug"])

    output = {
        "description": _DESCRIPTION,
        "publication": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": _SOURCES,
        "places": records,
    }

    changed, status = write_json_if_changed(
        output_path, output, exclude_fields=["publication"], indent=2
    )
    logger.info("places.json: %s (changed=%s)", status, changed)
    return changed, status


def _build_countries(
    tlds: list[dict],
    claimed: set[str],
    dependent_territories: dict[str, list[str]],
) -> dict[str, dict]:
    """Build country records keyed by ISO 3166-1 alpha-2 slug.

    Every delegated ccTLD folds into one record by its alpha-2 (uk -> gb; IDN
    ccTLDs join via tld_iso). TLDs claimed by an editorial place are skipped so
    they never get a spurious country record (e.g. .eu is supranational).
    """
    by_slug: dict[str, dict] = {}

    def ensure(slug: str) -> dict:
        if slug not in by_slug:
            iso = pycountry.countries.get(alpha_2=slug.upper())
            by_slug[slug] = {
                "slug": slug,
                "name_en": get_country_name(slug),
                "subtype": "country",
                "iso_code": iso.alpha_2 if iso else None,
                "iso_numeric": iso.numeric if iso else None,
                "parent": None,
                "tlds": [],
            }
        return by_slug[slug]

    for entry in tlds:
        tld = entry["tld"]
        if not entry.get("delegated") or tld in claimed:
            continue
        if is_cctld(tld):
            ensure("gb" if tld == "uk" else tld)["tlds"].append(tld)
        elif tld.startswith("xn--") and entry.get("tld_iso"):
            iso = entry["tld_iso"].lower()
            ensure("gb" if iso == "uk" else iso)["tlds"].append(tld)

    for slug, (designation, parent) in _SPECIAL.items():
        if slug in by_slug:
            by_slug[slug]["iso_designation"] = designation
            if parent is not None:
                by_slug[slug]["parent"] = parent

    for sovereign, territories in dependent_territories.items():
        for territory in territories:
            if territory in by_slug:
                by_slug[territory]["iso_designation"] = "dependent_territory"
                by_slug[territory]["parent"] = sovereign

    for record in by_slug.values():
        record["tlds"].sort()
    return by_slug


def _overlay_country_coordinates(
    countries: dict[str, dict], overlay: dict[str, dict]
) -> None:
    """Add `info_link` + `coordinates` from the overlay onto matching derived
    countries (additive; identity stays derived). Unknown slugs are logged, skipped."""
    for slug, data in overlay.items():
        record = countries.get(slug)
        if record is None:
            logger.warning("country-coordinates: no country %r to overlay", slug)
            continue
        for field in ("info_link", "coordinates"):
            if field in data:
                record[field] = data[field]


def _manual_records(manual_places: dict[str, dict]) -> list[dict]:
    """Normalize the editorial places into output records (sorted tlds).

    Carries `coordinates` through only when the entry provides it.
    """
    records = []
    for slug, rec in manual_places.items():
        record = {
            "slug": slug,
            "name_en": rec["name_en"],
            "subtype": rec["subtype"],
            "iso_code": rec.get("iso_code"),
            "parent": rec.get("parent"),
            "info_link": rec["info_link"],
            "tlds": sorted(rec["tlds"]),
        }
        if "coordinates" in rec:
            record["coordinates"] = rec["coordinates"]
        records.append(record)
    return records
