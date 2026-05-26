"""Build data/generated/cultures.json.

Merges the editorial culture identity (data/manual/cultures.json) with a reverse
index of TLDs transposed from each TLD's annotations.cultural_affiliation.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from ..utilities.content_changed import write_json_if_changed

logger = logging.getLogger(__name__)

_DESCRIPTION = (
    "Ethno-linguistic and cultural communities claimed by TLDs in the IANA root "
    "zone, each with a reverse index of those TLDs."
)

_SOURCES = [
    "data/manual/cultures.json (editorial)",
    "data/manual/annotations.json (cultural_affiliation tags)",
]


def build_cultures_json(
    tlds: list[dict], manual_cultures: dict[str, dict], output_path: Path
) -> tuple[bool, str]:
    """Attach the TLD reverse-index to the culture seed and write the file.

    Args:
        tlds: The built TLD entries (source of cultural_affiliation membership).
        manual_cultures: Editorial culture identity, keyed by slug.
        output_path: Destination for the generated artifact.

    Returns:
        The ``(changed, status)`` tuple from ``write_json_if_changed``.
    """
    tlds_by_slug = _transpose(tlds)

    cultures = []
    for slug in sorted(manual_cultures):
        rec = manual_cultures[slug]
        cultures.append(
            {
                "slug": slug,
                "name_en": rec["name_en"],
                "info_link": rec["info_link"],
                "language_code": rec.get("language_code"),
                "tlds": sorted(tlds_by_slug.get(slug, set())),
            }
        )

    output = {
        "description": _DESCRIPTION,
        "publication": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": _SOURCES,
        "cultures": cultures,
    }

    changed, status = write_json_if_changed(
        output_path, output, exclude_fields=["publication"], indent=2
    )
    logger.info("cultures.json: %s (changed=%s)", status, changed)
    return changed, status


def _transpose(tlds: list[dict]) -> dict[str, set[str]]:
    """Build ``{culture_slug: {tlds}}`` from each TLD's cultural_affiliation."""
    acc: dict[str, set[str]] = {}
    for entry in tlds:
        affiliation = entry.get("annotations", {}).get("cultural_affiliation")
        if affiliation:
            acc.setdefault(affiliation, set()).add(entry["tld"])
    return acc
