"""Tests for the TLD archive seed loader and its validation."""

import json
from typing import Any

import pytest

from src.parse.tld_archive import (
    TldArchiveError,
    parse_tld_archive,
    validate_tld_archive,
)

SPONSORED = {"value": "sponsored", "archived_on": "2026-11-10"}


def _write(tmp_path, data: Any):
    path = tmp_path / "tld-archive.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_validate_tld_archive_accepts_every_supported_shape():
    seed = {
        "com": {"tld_created": "1985-01-01"},
        "aero": {"tld_created": "2001-12-21", "archived": {"iana_tag": SPONSORED}},
        "arpa": {
            "archived": {
                "iana_tag": {"value": "infrastructure", "archived_on": "2026-11-10"}
            }
        },
        "biz": {
            "archived": {
                "iana_tag": {
                    "value": "generic-restricted",
                    "archived_on": "2026-11-10",
                }
            }
        },
    }

    assert validate_tld_archive(seed) == []


@pytest.mark.parametrize(
    ("seed", "fragment"),
    [
        ([], "expected an object"),
        ({"com": "1985-01-01"}, "com is str, expected an object"),
        ({"com": {}}, "com is empty"),
        ({"com": {"created": "1985-01-01"}}, "unknown key(s) ['created']"),
        ({"com": {"tld_created": "1985"}}, "tld_created is '1985'"),
        ({"com": {"tld_created": "19850101"}}, "tld_created is '19850101'"),
        ({"com": {"tld_created": "1985-02-30"}}, "is not a real date"),
        ({"com": {"tld_created": None}}, "tld_created is None"),
        ({"com": {"archived": []}}, "archived is list, expected an object"),
        ({"com": {"archived": {}}}, "archived is empty"),
        (
            {"com": {"archived": {"type": SPONSORED}}},
            "archived has unknown key(s) ['type']",
        ),
        (
            {"com": {"archived": {"iana_tag": "sponsored"}}},
            "archived.iana_tag is str, expected an object",
        ),
        (
            {"com": {"archived": {"iana_tag": {**SPONSORED, "note": "x"}}}},
            "archived.iana_tag has unknown key(s) ['note']",
        ),
        (
            {"com": {"archived": {"iana_tag": {"value": "sponsored"}}}},
            "archived.iana_tag is missing ['archived_on']",
        ),
        (
            {"com": {"archived": {"iana_tag": {"archived_on": "2026-11-10"}}}},
            "archived.iana_tag is missing ['value']",
        ),
        (
            {"com": {"archived": {"iana_tag": {**SPONSORED, "value": "generic"}}}},
            "archived.iana_tag value is 'generic'",
        ),
        (
            {"com": {"archived": {"iana_tag": {**SPONSORED, "value": 7}}}},
            "archived.iana_tag value is 7",
        ),
        (
            {"com": {"archived": {"iana_tag": {**SPONSORED, "value": []}}}},
            "archived.iana_tag value is []",
        ),
        (
            {"com": {"archived": {"iana_tag": {**SPONSORED, "value": {"a": 1}}}}},
            "archived.iana_tag value is {'a': 1}",
        ),
        (
            {"com": {"archived": {"iana_tag": {**SPONSORED, "value": None}}}},
            "archived.iana_tag value is None",
        ),
        (
            {
                "com": {
                    "archived": {"iana_tag": {**SPONSORED, "archived_on": "2026-13-01"}}
                }
            },
            "archived.iana_tag archived_on '2026-13-01' is not a real date",
        ),
        (
            {
                "com": {
                    "archived": {"iana_tag": {**SPONSORED, "archived_on": "20261110"}}
                }
            },
            "archived.iana_tag archived_on is '20261110', expected YYYY-MM-DD",
        ),
        ({"COM": {"tld_created": "1985-01-01"}}, "'COM' is not a lowercase"),
    ],
)
def test_validate_tld_archive_reports_each_problem(seed, fragment):
    problems = validate_tld_archive(seed)

    assert any(fragment in problem for problem in problems), problems


def test_validate_tld_archive_reports_every_problem_not_just_the_first():
    seed = {"aa": {"tld_created": "x"}, "bb": {"nope": 1}}

    assert len(validate_tld_archive(seed)) == 2


def test_parse_tld_archive_returns_the_seed(tmp_path):
    seed = {"aero": {"tld_created": "2001-12-21", "archived": {"iana_tag": SPONSORED}}}

    assert parse_tld_archive(_write(tmp_path, seed)) == seed


def test_parse_tld_archive_empty_object_is_valid(tmp_path):
    assert parse_tld_archive(_write(tmp_path, {})) == {}


def test_parse_tld_archive_invalid_seed_raises_with_every_problem(tmp_path):
    seed = {"aa": {"tld_created": "x"}, "bb": {"nope": 1}}

    with pytest.raises(TldArchiveError) as excinfo:
        parse_tld_archive(_write(tmp_path, seed))

    assert "aa" in str(excinfo.value)
    assert "bb" in str(excinfo.value)


def test_parse_tld_archive_missing_file_raises(tmp_path):
    """A missing seed must not read as "no TLD has a creation date"."""
    with pytest.raises(TldArchiveError, match="absent.json"):
        parse_tld_archive(tmp_path / "absent.json")


def test_parse_tld_archive_invalid_json_raises(tmp_path):
    path = tmp_path / "tld-archive.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(TldArchiveError, match="tld-archive.json"):
        parse_tld_archive(path)
