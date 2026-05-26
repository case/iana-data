"""Build data/generated/agreements.json.

Transposes the built TLD list into a per-agreement-type reverse index. The slug
and verbatim ICANN string come from REGISTRY_AGREEMENT_TYPE_MAPPING; the friendly
display_name is an editorial layer authored here.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from ..config import REGISTRY_AGREEMENT_TYPE_MAPPING
from ..utilities.content_changed import write_json_if_changed

logger = logging.getLogger(__name__)

_DESCRIPTION = (
    "ICANN registry-agreement types with a reverse index of the gTLDs operating "
    "under each. Slugs and source_names are canonical ICANN values; display_name "
    "is a friendly editorial label."
)

_SOURCES = [
    "data/source/icann-registry-agreement-table.csv (ICANN)",
]

# Friendly display label per slug. Must cover every slug in
# REGISTRY_AGREEMENT_TYPE_MAPPING; a missing entry fails the build (KeyError).
_DISPLAY_NAMES: dict[str, str] = {
    "base": "Base",
    "non_sponsored": "Non-Sponsored",
    "brand": "Brand",
    "community": "Community",
    "sponsored": "Sponsored",
}


def build_agreements_json(tlds: list[dict], output_path: Path) -> tuple[bool, str]:
    """Transpose registry-agreement types and write agreements.json.

    Args:
        tlds: The built TLD entries (the source of agreement-type relationships).
        output_path: Destination for the generated artifact.

    Returns:
        The ``(changed, status)`` tuple from ``write_json_if_changed``.
    """
    # slug -> verbatim ICANN string (the inverse of the source mapping).
    source_strings = {
        slug: raw for raw, slug in REGISTRY_AGREEMENT_TYPE_MAPPING.items()
    }
    tlds_by_slug = _transpose(tlds)

    agreements = []
    for slug in sorted(source_strings):
        agreements.append(
            {
                "slug": slug,
                "display_name": _DISPLAY_NAMES[slug],
                "source_names": {"icann": source_strings[slug]},
                "tlds": sorted(tlds_by_slug.get(slug, set())),
            }
        )

    output = {
        "description": _DESCRIPTION,
        "publication": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": _SOURCES,
        "agreements": agreements,
    }

    changed, status = write_json_if_changed(
        output_path, output, exclude_fields=["publication"], indent=2
    )
    logger.info("agreements.json: %s (changed=%s)", status, changed)
    return changed, status


def _transpose(tlds: list[dict]) -> dict[str, set[str]]:
    """Build ``{slug: {tlds}}`` from each TLD's registry_agreement_types."""
    acc: dict[str, set[str]] = {}
    for entry in tlds:
        for slug in entry.get("annotations", {}).get("registry_agreement_types", []):
            acc.setdefault(slug, set()).add(entry["tld"])
    return acc
