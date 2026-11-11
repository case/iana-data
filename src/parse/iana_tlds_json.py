"""Parser for the IANA TLD JSON export (https://data.iana.org/TLD/v1/tlds.json).

Fails closed: an unknown status, type or specversion, a missing key the build
reads, a wrong type, or a broken cross-field rule of the schema raises
IanaTldsError. Unknown keys are ignored, as the schema's specversion note requires.
"""

import ipaddress
import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..config import SOURCE_DIR, SOURCE_FILES

logger = logging.getLogger(__name__)

SPEC_VERSION = 1
STATUSES: frozenset[str] = frozenset({"active", "retired", "eligible", "reserved"})
TYPES: frozenset[str] = frozenset({"generic", "country-code", "special-use", "test"})

# The name becomes a file name under data/generated/tld/, so it is an LDH label.
_NAME = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
_SCRIPT_CODE = re.compile(r"[A-Z][a-z]{3}")
_ISO3166_CODE = re.compile(r"[A-Z]{2}")
# The schema's own hostname pattern. It does not bound a label's length.
_HOSTNAME = re.compile(
    r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+"
)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_EVENT_DATE = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")


class IanaTldsError(ValueError):
    """The IANA TLD JSON is unreadable or does not have the expected shape."""


@dataclass(frozen=True, slots=True)
class IanaNameserver:
    """A name server delegated in the root zone, with its glue addresses."""

    name: str
    ipv4: tuple[str, ...]
    ipv6: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IanaDsRecord:
    """A DS record published in the root zone."""

    key_tag: int
    algorithm: int
    digest_type: int
    digest: str


@dataclass(frozen=True, slots=True)
class IanaTld:
    """One TLD record, reduced to the fields the build reads.

    ``manager``, ``admin`` and ``tech`` are organization names. ``delegation``
    and ``revocation`` are ISO 8601 dates at year, month or day precision.
    """

    name: str
    status: str
    type: str
    script_code: str
    ulabel: str | None
    iso3166_code: str | None
    delegation_round: str | None
    language_code: str | None
    transliteration: str | None
    translation: str | None
    manager: str | None
    admin: str | None
    tech: str | None
    nameservers: tuple[IanaNameserver, ...]
    ds_records: tuple[IanaDsRecord, ...]
    rdap_base_urls: tuple[str, ...]
    whois_server: str | None
    registration_url: str | None
    purpose: str | None
    remarks: str | None
    delegation: str | None
    revocation: str | None
    last_updated: str | None


def _require(obj: dict[str, Any], key: str, where: str) -> Any:
    if key not in obj:
        raise IanaTldsError(f"{where} is missing required key {key!r}")
    return obj[key]


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IanaTldsError(f"{where} is {type(value).__name__}, expected an object")
    return value


def _array(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise IanaTldsError(f"{where} is {type(value).__name__}, expected an array")
    return value


def _string(value: Any, where: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str):
        raise IanaTldsError(f"{where} is {type(value).__name__}, expected a string")
    if pattern is not None and not pattern.fullmatch(value):
        raise IanaTldsError(f"{where} is {value!r}, which is not the expected format")
    return value


def _nullable_string(
    value: Any, where: str, pattern: re.Pattern[str] | None = None
) -> str | None:
    return None if value is None else _string(value, where, pattern)


def _optional_string(
    obj: dict[str, Any], key: str, where: str, pattern: re.Pattern[str] | None = None
) -> str | None:
    """A string for a key that may be absent; present-but-null is a wrong type."""
    return _string(obj[key], f"{where}.{key}", pattern) if key in obj else None


def _integer(value: Any, where: str) -> int:
    # bool is an int subclass, and JSON true is not a key tag.
    if isinstance(value, bool) or not isinstance(value, int):
        raise IanaTldsError(f"{where} is {type(value).__name__}, expected an integer")
    return value


def _enum(value: Any, where: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise IanaTldsError(f"{where} is {value!r}, expected one of {sorted(allowed)}")
    return value


def _calendar_date(value: Any, where: str) -> str | None:
    text = _nullable_string(value, where, _DATE)
    if text is not None:
        try:
            date.fromisoformat(text)
        except ValueError as exc:
            raise IanaTldsError(f"{where} {text!r} is not a real date: {exc}") from exc
    return text


def _event_date(value: Any, where: str) -> str | None:
    """An ISO 8601 date at year, month or day precision, checked as a real date."""
    text = _nullable_string(value, where, _EVENT_DATE)
    if text is not None:
        # Pad a year or year-month to its first day, so one check covers all three.
        padded = text + "-01-01"[len(text) - 4 :]
        try:
            date.fromisoformat(padded)
        except ValueError as exc:
            raise IanaTldsError(f"{where} {text!r} is not a real date: {exc}") from exc
    return text


def _check_conditional_rules(record: "IanaTld", where: str, delegated: bool) -> None:
    """Enforce the schema's cross-field rules; ``delegated`` means manager and contacts."""
    problems = []
    if record.status == "active":
        if not delegated:
            problems.append("is active without a manager and contacts")
        if not record.nameservers:
            problems.append("is active without nameservers")
    elif record.nameservers or record.ds_records:
        problems.append(f"is {record.status} but has nameservers or DS records")
    if record.status == "retired" and record.revocation is None:
        problems.append("is retired without a revocation date")
    if record.status == "reserved" and record.purpose is None:
        problems.append("is reserved without a purpose")
    if record.name.startswith("xn--"):
        if record.ulabel is None:
            problems.append("is an IDN without a ulabel")
        if record.type == "country-code" and record.iso3166_code is None:
            problems.append("is an IDN ccTLD without an iso3166_code")
    if problems:
        raise IanaTldsError(f"{where} " + "; ".join(problems))


def _http_url(value: Any, where: str) -> str:
    """An http or https URL that names a host and has a usable port, if any."""
    text = _string(value, where)
    try:
        parts = urlsplit(text)
        # Reading .port raises ValueError for a port that is not a number in range.
        usable = parts.scheme in {"http", "https"} and bool(parts.hostname)
        usable = usable and (parts.port is None or parts.port > 0)
    except ValueError:
        usable = False
    if not usable or any(char.isspace() for char in text):
        raise IanaTldsError(f"{where} is {text!r}, not an http(s) URL with a host")
    return text


def _hostname(value: Any, where: str) -> str:
    """A lower-case LDH host name of two or more labels, within DNS length limits."""
    text = _string(value, where, _HOSTNAME)
    if len(text) > 253 or any(len(label) > 63 for label in text.split(".")):
        raise IanaTldsError(f"{where} is {text!r}, longer than a DNS name allows")
    return text


def _addresses(value: Any, where: str, family: type) -> tuple[str, ...]:
    """Addresses of one family, in compressed form."""
    out: list[str] = []
    for index, item in enumerate(_array(value, where)):
        text = _string(item, f"{where}[{index}]")
        try:
            out.append(str(family(text)))
        except ValueError as exc:
            raise IanaTldsError(
                f"{where}[{index}] is {text!r}, not a valid address"
            ) from exc
    return tuple(out)


def _organization(value: Any, where: str) -> str | None:
    """The organization of a manager or contact object."""
    obj = _object(value, where)
    return _nullable_string(
        _require(obj, "organization", where), f"{where}.organization"
    )


def _nameserver(value: Any, where: str) -> IanaNameserver:
    obj = _object(value, where)
    return IanaNameserver(
        name=_hostname(_require(obj, "name", where), f"{where}.name"),
        ipv4=_addresses(
            _require(obj, "ipv4", where), f"{where}.ipv4", ipaddress.IPv4Address
        ),
        ipv6=_addresses(
            _require(obj, "ipv6", where), f"{where}.ipv6", ipaddress.IPv6Address
        ),
    )


def _ds_record(value: Any, where: str) -> IanaDsRecord:
    obj = _object(value, where)
    return IanaDsRecord(
        key_tag=_integer(_require(obj, "key_tag", where), f"{where}.key_tag"),
        algorithm=_integer(_require(obj, "algorithm", where), f"{where}.algorithm"),
        digest_type=_integer(
            _require(obj, "digest_type", where), f"{where}.digest_type"
        ),
        digest=_string(_require(obj, "digest", where), f"{where}.digest"),
    )


def _domain(value: Any, index: int) -> IanaTld:
    where = f"domains[{index}]"
    obj = _object(value, where)
    name = _string(_require(obj, "name", where), f"{where}.name", _NAME)
    where = f"domains[{index}] ({name})"

    annotations = _object(_require(obj, "annotations", where), f"{where}.annotations")
    manager = _require(obj, "manager", where)
    contacts = _require(obj, "contacts", where)
    admin = tech = None
    if contacts is not None:
        contacts = _object(contacts, f"{where}.contacts")
        admin = _organization(
            _require(contacts, "admin", f"{where}.contacts"), f"{where}.contacts.admin"
        )
        tech = _organization(
            _require(contacts, "tech", f"{where}.contacts"), f"{where}.contacts.tech"
        )
    events = _object(_require(obj, "events", where), f"{where}.events")

    record = IanaTld(
        name=name,
        status=_enum(_require(obj, "status", where), f"{where}.status", STATUSES),
        type=_enum(_require(obj, "type", where), f"{where}.type", TYPES),
        script_code=_string(
            _require(obj, "script_code", where), f"{where}.script_code", _SCRIPT_CODE
        ),
        ulabel=_optional_string(obj, "ulabel", where),
        iso3166_code=_optional_string(obj, "iso3166_code", where, _ISO3166_CODE),
        delegation_round=_optional_string(
            annotations, "delegation_round", f"{where}.annotations"
        ),
        language_code=_optional_string(
            annotations, "language_code", f"{where}.annotations"
        ),
        transliteration=_optional_string(
            annotations, "transliteration", f"{where}.annotations"
        ),
        translation=_optional_string(
            annotations, "translation", f"{where}.annotations"
        ),
        manager=(
            None if manager is None else _organization(manager, f"{where}.manager")
        ),
        admin=admin,
        tech=tech,
        nameservers=tuple(
            _nameserver(item, f"{where}.nameservers[{i}]")
            for i, item in enumerate(
                _array(_require(obj, "nameservers", where), f"{where}.nameservers")
            )
        ),
        ds_records=tuple(
            _ds_record(item, f"{where}.ds_records[{i}]")
            for i, item in enumerate(
                _array(_require(obj, "ds_records", where), f"{where}.ds_records")
            )
        ),
        rdap_base_urls=tuple(
            _http_url(item, f"{where}.rdap_base_urls[{i}]")
            for i, item in enumerate(
                _array(
                    _require(obj, "rdap_base_urls", where), f"{where}.rdap_base_urls"
                )
            )
        ),
        whois_server=(
            None
            if _require(obj, "whois_server", where) is None
            else _hostname(obj["whois_server"], f"{where}.whois_server")
        ),
        registration_url=_nullable_string(
            _require(obj, "registration_url", where), f"{where}.registration_url"
        ),
        purpose=_optional_string(obj, "purpose", where),
        remarks=_optional_string(obj, "remarks", where),
        delegation=_event_date(
            _require(events, "delegation", f"{where}.events"),
            f"{where}.events.delegation",
        ),
        revocation=_event_date(
            _require(events, "revocation", f"{where}.events"),
            f"{where}.events.revocation",
        ),
        last_updated=_calendar_date(
            _require(obj, "last_updated", where), f"{where}.last_updated"
        ),
    )
    _check_conditional_rules(
        record, where, delegated=manager is not None and contacts is not None
    )
    return record


def parse_iana_tlds(document: Any) -> list[IanaTld]:
    """Parse a decoded IANA TLD JSON document into records, in document order.

    Raises:
        IanaTldsError: the document is not the expected shape, carries an
            unknown specversion, status or type, has no records, or repeats a name.
    """
    root = _object(document, "document")
    meta = _object(_require(root, "meta", "document"), "meta")
    specversion = _require(meta, "specversion", "meta")
    if isinstance(specversion, bool) or not isinstance(specversion, int):
        raise IanaTldsError(f"meta.specversion is {specversion!r}, expected an integer")
    if specversion != SPEC_VERSION:
        raise IanaTldsError(
            f"meta.specversion is {specversion}, this parser reads {SPEC_VERSION}"
        )

    domains = _array(_require(root, "domains", "document"), "domains")
    if not domains:
        raise IanaTldsError("domains is empty")

    records: list[IanaTld] = []
    seen: set[str] = set()
    for index, item in enumerate(domains):
        record = _domain(item, index)
        if record.name in seen:
            raise IanaTldsError(f"domains[{index}] is a duplicate of {record.name!r}")
        seen.add(record.name)
        records.append(record)
    return records


def load_iana_tlds(filepath: Path | None = None) -> list[IanaTld]:
    """Read and parse the IANA TLD JSON file.

    Args:
        filepath: Path to the file (defaults to the configured source location).

    Raises:
        IanaTldsError: the file is missing, unreadable, not JSON, or rejected
            by ``parse_iana_tlds``. Never returns an empty list.
    """
    if filepath is None:
        filepath = Path(SOURCE_DIR) / SOURCE_FILES["IANA_TLDS"]
    try:
        document = json.loads(filepath.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IanaTldsError(f"cannot read {filepath}: {exc}") from exc
    try:
        return parse_iana_tlds(document)
    except IanaTldsError as exc:
        raise IanaTldsError(f"{filepath}: {exc}") from exc


def _without_generated(document: Any) -> Any:
    """The document minus ``meta.generated``, the only field that is a timestamp."""
    if isinstance(document, dict) and isinstance(document.get("meta"), dict):
        meta = {k: v for k, v in document["meta"].items() if k != "generated"}
        return {**document, "meta": meta}
    return document


def iana_tlds_json_content_changed(filepath: Path, new_content: str) -> bool:
    """Whether new IANA TLD JSON differs from the stored file, ignoring meta.generated.

    Returns:
        True when the data differs, when there is no readable stored file, or
        when either side is not JSON. False only for a timestamp-only change.
    """
    if not filepath.exists():
        return True
    try:
        new_document = json.loads(new_content)
    except ValueError as exc:
        logger.error("Error parsing new IANA TLD JSON content: %s", exc)
        return True
    try:
        existing_document = json.loads(filepath.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Error reading existing IANA TLD JSON %s: %s", filepath, exc)
        return True

    if _without_generated(new_document) == _without_generated(existing_document):
        logger.info("IANA TLD JSON unchanged (only meta.generated updated)")
        return False
    return True
