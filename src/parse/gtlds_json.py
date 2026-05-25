"""Parser for the ICANN gTLDs JSON Report.

Source: https://www.icann.org/resources/registries/gtlds/v2/gtlds.json
Produces the per-TLD ``orgs.icann.*`` subobject, mapping the upstream camelCase
fields to the project's snake_case schema. Two upstream fields are deliberately
omitted: ``registryClassDomainNameList`` (null in every record, with no published
documentation of its meaning) and ``uLabel`` (used only as a verification oracle
for the locally computed Unicode label, not stored here).
"""

import json
import logging
from pathlib import Path
from typing import TypedDict

from ..config import SOURCE_DIR, SOURCE_FILES

logger = logging.getLogger(__name__)


class GtldRecord(TypedDict):
    """Parsed ICANN gTLD record (the ``orgs.icann.*`` subobject for one TLD).

    Nulls are preserved from the source: a null typically means "no active
    contract" (terminated TLDs carry null operator/spec_13/dates). Only
    ``contract_terminated`` is guaranteed non-null (always bool).
    """

    registry_operator: str | None
    specification_13: bool | None
    third_or_lower_level_registration: bool | None
    application_id: str | None
    registry_operator_country_code: str | None
    date_contract_signed: str | None
    date_delegated: str | None
    contract_terminated: bool
    date_removed: str | None


def parse_gtlds_json(filepath: Path | None = None) -> dict[str, GtldRecord]:
    """Parse the ICANN gTLDs JSON Report into a TLD-keyed lookup map.

    Args:
        filepath: Path to the JSON file (defaults to the configured source).

    Returns:
        Map of bare lowercase TLD (no leading dot) to its parsed record.
    """
    if filepath is None:
        filepath = Path(SOURCE_DIR) / SOURCE_FILES["GTLDS_JSON"]

    if not filepath.exists():
        logger.warning("gTLDs JSON not found at %s", filepath)
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Error parsing gTLDs JSON from %s: %s", filepath, e)
        return {}

    records: dict[str, GtldRecord] = {}
    for row in payload.get("gTLDs", []):
        tld = (row.get("gTLD") or "").strip().lower()
        if not tld:
            continue
        records[tld] = {
            "registry_operator": row.get("registryOperator"),
            "specification_13": row.get("specification13"),
            "third_or_lower_level_registration": row.get(
                "thirdOrLowerLevelRegistration"
            ),
            "application_id": row.get("applicationId"),
            "registry_operator_country_code": row.get("registryOperatorCountryCode"),
            "date_contract_signed": row.get("dateOfContractSignature"),
            "date_delegated": row.get("delegationDate"),
            "contract_terminated": bool(row.get("contractTerminated")),
            "date_removed": row.get("removalDate"),
        }

    logger.info("Parsed %d gTLD records from JSON", len(records))
    return records
