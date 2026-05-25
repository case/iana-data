"""Parser and resolver for the editorial organizations seed.

Reads data/manual/organizations.json (identity only; the build adds roles) and
indexes it so a raw per-source org string resolves to one canonical record.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import MANUAL_DIR, MANUAL_FILES
from ..utilities.file_io import read_json_file

logger = logging.getLogger(__name__)

OrgRecord = dict[str, Any]

# The provenance buckets shared by source_names and roles.
SOURCES: tuple[str, ...] = ("iana", "icann", "asn")


def parse_organizations_manual(filepath: Path | None = None) -> list[OrgRecord]:
    """Parse the editorial organizations file into a list of records.

    Args:
        filepath: Path to organizations.json (defaults to the configured location).

    Returns:
        The org records as authored (identity only; the build adds ``roles``).
        An empty list if the file is missing or not a JSON array.
    """
    if filepath is None:
        filepath = Path(MANUAL_DIR) / MANUAL_FILES["ORGANIZATIONS"]

    data = read_json_file(filepath, default=[])
    if not isinstance(data, list):
        logger.error("organizations.json is not a JSON array: %s", filepath)
        return []
    return data


@dataclass(frozen=True)
class OrgResolver:
    """Resolves a raw per-source org string to one canonical record.

    Keys per bucket are its source_names plus display_name/aliases; collisions
    lists any string two orgs claim in one bucket (the integrity tests reject any).
    """

    by_source: dict[str, dict[str, OrgRecord]]
    collisions: list[tuple[str, str, str, str]]

    def resolve(self, source: str, name: str | None) -> OrgRecord | None:
        """Return the org a raw ``name`` resolves to in ``source``, or None."""
        if not name:
            return None
        return self.by_source.get(source, {}).get(name)


def build_resolver(orgs: list[OrgRecord]) -> OrgResolver:
    """Build an OrgResolver from manual org records.

    A key claimed by two different slugs within one bucket is recorded in
    ``collisions`` and the first claimant is kept (deterministic, never silently
    overwritten).
    """
    by_source: dict[str, dict[str, OrgRecord]] = {source: {} for source in SOURCES}
    collisions: list[tuple[str, str, str, str]] = []

    for org in orgs:
        slug = org["slug"]
        source_names = org.get("source_names", {})
        fallbacks = [org["display_name"], *org.get("aliases", [])]
        for source in SOURCES:
            for name in [*source_names.get(source, []), *fallbacks]:
                existing = by_source[source].get(name)
                if existing is not None and existing["slug"] != slug:
                    collisions.append((source, name, existing["slug"], slug))
                    continue
                by_source[source][name] = org

    if collisions:
        logger.warning(
            "organizations.json: %d ambiguous source_name(s) across orgs: %s",
            len(collisions),
            collisions[:5],
        )
    return OrgResolver(by_source=by_source, collisions=collisions)
