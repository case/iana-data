"""Parser for ICANN Registry Agreement Table CSV file."""

import csv
import logging
from pathlib import Path
from typing import TypedDict

from ..config import REGISTRY_AGREEMENT_TYPE_MAPPING, SOURCE_DIR, SOURCE_FILES

logger = logging.getLogger(__name__)


class RegistryAgreement(TypedDict, total=False):
    """Type for parsed registry agreement entry."""

    tld: str
    u_label: str
    translation: str
    agreement_types: list[str]
    operator: str
    status: str
    agreement_date: str
    link: str


def parse_agreement_types(raw_types: str) -> list[str]:
    """
    Parse comma-separated agreement types into normalized list.

    Args:
        raw_types: Raw agreement type string like "Base, Brand (Spec 13), Non-Sponsored"

    Returns:
        list: Parsed type strings (e.g., ["Base", "Brand (Spec 13)", "Non-Sponsored"])
    """
    if not raw_types:
        return []
    return [t.strip() for t in raw_types.split(",") if t.strip()]


def get_normalized_agreement_types(agreement_types: list[str]) -> list[str]:
    """
    Get normalized agreement type annotation values from parsed types.

    Maps raw agreement types to normalized values using the config mapping.
    Returns all matching normalized types in the order they appear.

    Args:
        agreement_types: List of parsed agreement types (raw strings from CSV)

    Returns:
        List of normalized type strings (e.g., ["base", "brand", "non_sponsored"])
    """
    normalized = []
    for raw_type in agreement_types:
        if raw_type in REGISTRY_AGREEMENT_TYPE_MAPPING:
            normalized.append(REGISTRY_AGREEMENT_TYPE_MAPPING[raw_type])
    return normalized


def parse_registry_agreement_csv(
    filepath: Path | None = None,
) -> dict[str, RegistryAgreement]:
    """
    Parse the ICANN Registry Agreement Table CSV into a TLD lookup map.

    Args:
        filepath: Path to the CSV file (defaults to configured location)

    Returns:
        dict: Map of TLD (lowercase, without leading dot) to agreement data
    """
    if filepath is None:
        filepath = Path(SOURCE_DIR) / SOURCE_FILES["REGISTRY_AGREEMENT_TABLE"]

    if not filepath.exists():
        logger.warning("Registry agreement CSV not found at %s", filepath)
        return {}

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            agreements: dict[str, RegistryAgreement] = {}

            for row in reader:
                tld = row.get("Top Level Domain", "").strip().lower()
                if not tld:
                    continue

                entry: RegistryAgreement = {
                    "tld": tld,
                    "agreement_types": parse_agreement_types(row.get("Agreement Type", "")),
                    "status": row.get("Agreement Status", "").strip().lower(),
                }

                # Add optional fields if present
                if row.get("U-Label"):
                    entry["u_label"] = row["U-Label"].strip()
                if row.get("Translation"):
                    entry["translation"] = row["Translation"].strip()
                if row.get("Operator"):
                    entry["operator"] = row["Operator"].strip()
                if row.get("Agreement Date"):
                    entry["agreement_date"] = row["Agreement Date"].strip()
                if row.get("Link"):
                    entry["link"] = row["Link"].strip()

                agreements[tld] = entry

            logger.info("Parsed %d registry agreements from CSV", len(agreements))
            return agreements

    except (OSError, csv.Error) as e:
        logger.error("Error parsing registry agreement CSV from %s: %s", filepath, e)
        return {}
