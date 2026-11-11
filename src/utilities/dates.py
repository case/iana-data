"""Date validation shared by the hand-curated seed files."""

import re
from datetime import date
from typing import Any

# date.fromisoformat also accepts "20260912", which a seed must not carry.
_ISO_DATE_SHAPE = re.compile(r"\d{4}-\d{2}-\d{2}")


def iso_date_problem(value: Any) -> str | None:
    """Why ``value`` is not a real YYYY-MM-DD date, or None when it is one.

    The text is a predicate, so a caller prefixes it with the field it names.
    """
    if not isinstance(value, str) or not _ISO_DATE_SHAPE.fullmatch(value):
        return f"is {value!r}, expected YYYY-MM-DD"
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        return f"{value!r} is not a real date: {exc}"
    return None
