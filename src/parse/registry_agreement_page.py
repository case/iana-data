"""Renderer for the ICANN registry agreement table, from the source page's embedded state.

Source: https://www.icann.org/en/registry-agreements
ICANN's ``/csvdownload`` endpoint has returned HTTP 502 since at least 2026-07-30.
The site's own download link builds the CSV in the browser from the server-rendered
``ng-state`` JSON, which this module reproduces byte for byte.
See docs/memory/log/2026-09-07-registry-agreement-csv.md.
"""

import json
import logging
import re
from datetime import date
from typing import Any, Final

from selectolax.parser import HTMLParser as SelectolaxParser

from ..config import REGISTRY_AGREEMENT_TYPE_MAPPING

logger = logging.getLogger(__name__)

NG_STATE_SELECTOR: Final[str] = "script#ng-state"
NG_STATE_KEY: Final[str] = "registry-agreements-{}"
DETAILS_BASE_URL: Final[str] = "https://www.icann.org/en/registry-agreements"

CSV_HEADER: Final[tuple[str, ...]] = (
    "Top Level Domain",
    "U-Label",
    "Translation",
    "Agreement Type",
    "Operator",
    "Agreement Status",
    "Agreement Date",
    "Link",
)

# Upstream emits these in arbitrary order; the page sorts them before display.
# Derived, so a new ICANN type cannot be added to one list and not the other.
AGREEMENT_TYPE_ORDER: Final[tuple[str, ...]] = tuple(REGISTRY_AGREEMENT_TYPE_MAPPING)

MONTH_ABBREVIATIONS: Final[tuple[str, ...]] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

TERMINATED_STATUS: Final[str] = "terminated"

# A TLD is interpolated into a URL path, so it is constrained to LDH labels.
TLD_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class RegistryAgreementPageError(Exception):
    """Raised when the registry agreement page does not have the expected shape."""


def extract_registry_agreements(html: str) -> list[dict[str, Any]]:
    """Extract the registry agreement records embedded in the page.

    Args:
        html: Full HTML of the ICANN registry agreements page.

    Returns:
        The upstream records, in the order the page delivered them.

    Raises:
        RegistryAgreementPageError: If the embedded state is absent, unparseable,
            missing the expected key path, or empty.
    """
    node = SelectolaxParser(html).css_first(NG_STATE_SELECTOR)
    if node is None:
        raise RegistryAgreementPageError(
            f"no {NG_STATE_SELECTOR} element on the registry agreements page"
        )

    try:
        state = json.loads(node.text())
    except json.JSONDecodeError as e:
        raise RegistryAgreementPageError(
            f"embedded {NG_STATE_SELECTOR} JSON is unparseable"
        ) from e

    try:
        records = state[NG_STATE_KEY]["data"]["registryAgreementOperations"][
            "registryAgreements"
        ]
    except (KeyError, TypeError) as e:
        raise RegistryAgreementPageError(
            f"embedded state has no {NG_STATE_KEY} registryAgreements path"
        ) from e

    if not isinstance(records, list):
        raise RegistryAgreementPageError(
            f"registryAgreements is {type(records).__name__}, expected a list"
        )
    if not records:
        raise RegistryAgreementPageError("registryAgreements is empty")

    logger.info("Extracted %d registry agreements from page state", len(records))
    return records


def render_registry_agreement_csv(html: str) -> bytes:
    """Render the registry agreement table exactly as the ICANN page's own export does.

    Args:
        html: Full HTML of the ICANN registry agreements page.

    Returns:
        UTF-8 bytes with a BOM, LF line endings and no trailing newline.

    Raises:
        RegistryAgreementPageError: If the page structure or any record is malformed.
    """
    records = extract_registry_agreements(html)
    rows = [",".join(_csv_field(value) for value in CSV_HEADER)]
    rows.extend(
        ",".join(_csv_field(value) for value in _row(record))
        for record in sorted(records, key=_sort_key)
    )
    return ("\ufeff" + "\n".join(rows)).encode("utf-8")


def _sort_key(record: dict[str, Any]) -> str:
    return _tld(record)


def _row(record: dict[str, Any]) -> tuple[str, ...]:
    """Build one output row from an upstream record."""
    tld = _tld(record)
    u_label = str(record.get("uLabel") or "")
    status = str(record.get("agreementStatus") or "").lower()
    segment = "terminated" if status == TERMINATED_STATUS else "details"

    return (
        tld,
        "" if u_label == tld else u_label,
        str(record.get("translation") or ""),
        _order_agreement_types(record.get("agreementType")),
        str(record.get("operator") or ""),
        status,
        _format_agreement_date(record.get("agreementDate")),
        f"{DETAILS_BASE_URL}/{segment}/{tld}",
    )


def _tld(record: dict[str, Any]) -> str:
    """Return the record's TLD, rejecting anything unsafe to place in a URL path."""
    tld = str(record.get("topLevelDomain") or "")
    if not TLD_PATTERN.fullmatch(tld):
        raise RegistryAgreementPageError(f"invalid top-level domain: {tld!r}")
    return tld


def _order_agreement_types(raw: object) -> str:
    """Sort agreement types into display order, raising on an unranked type."""
    parts = [part.strip() for part in str(raw or "").split(",") if part.strip()]
    unknown = [part for part in parts if part not in AGREEMENT_TYPE_ORDER]
    if unknown:
        raise RegistryAgreementPageError(f"unknown agreement type(s): {unknown}")
    return ", ".join(sorted(parts, key=AGREEMENT_TYPE_ORDER.index))


def _format_agreement_date(raw: object) -> str:
    """Format an ISO date the way the page does, locale-independently."""
    if not raw:
        return ""
    try:
        parsed = date.fromisoformat(str(raw))
    except ValueError as e:
        raise RegistryAgreementPageError(f"invalid agreement date: {raw!r}") from e
    return f"{parsed.day} {MONTH_ABBREVIATIONS[parsed.month - 1]} {parsed.year}"


def _csv_field(value: str) -> str:
    """Quote one field the way the page's exporter does: empty fields stay bare."""
    if not value:
        return ""
    return '"' + value.replace('"', '""') + '"'
