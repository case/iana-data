"""Validate IANA TLD JSON against IANA's own JSON Schema, with the canonical validator.

The downloader uses this before a fetched file replaces the stored one. The
hand-written parser in iana_tlds_json.py reads the fields the build needs; this
is what decides whether a document is the format IANA says it is.
"""

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable

from ..config import IANA_URLS

# Valid except for its one record, which has only a name. The meta is complete,
# so a schema can reject this document only by constraining TLD records.
_HOLLOW_DOCUMENT: dict[str, Any] = {
    "meta": {
        "generated": "2026-01-01T00:00:00Z",
        "source": "https://www.iana.org/domains/root/db",
        "schema": IANA_URLS["IANA_TLDS_SCHEMA"],
        "specversion": 1,
    },
    "domains": [{"name": "example"}],
}


_EXTERNAL_REFERENCE = "schema refers outside itself:"


def _validator(schema: Any) -> Draft202012Validator:
    # An empty registry: a $ref outside the schema is refused, never fetched.
    # Formats are assertions only with a checker; format-nongpl supplies them.
    return Draft202012Validator(
        schema,
        registry=Registry(),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def iana_tlds_schema_problems(schema: Any) -> list[str]:
    """Why ``schema`` is not usable as IANA's TLD JSON schema; empty when it is.

    It must be a valid JSON Schema, carry IANA's ``$id``, and reject a record
    with no fields. An empty object is a valid schema that accepts everything.
    """
    if not isinstance(schema, dict):
        return [f"schema is a JSON {type(schema).__name__}, expected an object"]
    expected_id = IANA_URLS["IANA_TLDS_SCHEMA"]
    if schema.get("$id") != expected_id:
        return [f"schema $id is {schema.get('$id')!r}, expected {expected_id!r}"]
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"schema is not a valid JSON Schema: {exc.message}"]
    probe = iana_tlds_conformance_problems(_HOLLOW_DOCUMENT, schema, limit=1)
    if not probe:
        return ["schema accepts a TLD record that has no fields"]
    if probe[0].startswith(_EXTERNAL_REFERENCE):
        return probe
    return []


def iana_tlds_conformance_problems(
    document: Any, schema: Any, limit: int = 5
) -> list[str]:
    """Up to ``limit`` ways ``document`` breaks ``schema``; empty when it conforms.

    A schema that refers outside itself is reported as a problem, not followed.
    """
    problems: list[str] = []
    try:
        for error in _validator(schema).iter_errors(document):
            problems.append(f"{error.json_path}: {error.message[:200]}")
            if len(problems) >= limit:
                break
    except Unresolvable as exc:
        return [f"{_EXTERNAL_REFERENCE} {exc.ref!r}"]
    return problems
