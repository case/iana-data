"""Tests for the dated-fixture lookup helper."""

from pathlib import Path

import pytest

from tests.dated_fixtures import latest_fixture

CORE_FIXTURES = Path(__file__).parent / "fixtures" / "source" / "core"


def _touch(directory: Path, *names: str) -> None:
    for name in names:
        (directory / name).write_text("{}", encoding="utf-8")


def test_latest_fixture_single_match_returns_it(tmp_path):
    _touch(tmp_path, "2026-11-10-iana-tlds.json")

    assert latest_fixture(tmp_path, "iana-tlds.json").name == (
        "2026-11-10-iana-tlds.json"
    )


def test_latest_fixture_several_dates_returns_the_latest(tmp_path):
    _touch(
        tmp_path,
        "2026-02-01-iana-tlds.json",
        "2026-11-10-iana-tlds.json",
        "2025-12-31-iana-tlds.json",
    )

    assert latest_fixture(tmp_path, "iana-tlds.json").name == (
        "2026-11-10-iana-tlds.json"
    )


def test_latest_fixture_empty_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"iana-tlds\.json"):
        latest_fixture(tmp_path, "iana-tlds.json")


@pytest.mark.parametrize(
    "near_miss",
    [
        "2026-11-10-iana-tlds-schema.json",
        "2026-11-10-x-iana-tlds.json",
        "2026-11-10-iana-tlds.json.bak",
        "iana-tlds.json",
        "2026-11-iana-tlds.json",
    ],
)
def test_latest_fixture_near_miss_slug_is_not_a_match(tmp_path, near_miss):
    _touch(tmp_path, near_miss)

    with pytest.raises(FileNotFoundError):
        latest_fixture(tmp_path, "iana-tlds.json")


def test_latest_fixture_near_miss_does_not_shadow_the_exact_slug(tmp_path):
    _touch(
        tmp_path,
        "2026-11-10-iana-tlds.json",
        "2026-12-01-iana-tlds-schema.json",
    )

    assert latest_fixture(tmp_path, "iana-tlds.json").name == (
        "2026-11-10-iana-tlds.json"
    )


def test_latest_fixture_ignores_a_directory_with_a_matching_name(tmp_path):
    _touch(tmp_path, "2026-01-01-iana-tlds.json")
    (tmp_path / "2026-12-01-iana-tlds.json").mkdir()

    assert latest_fixture(tmp_path, "iana-tlds.json").name == (
        "2026-01-01-iana-tlds.json"
    )


def test_latest_fixture_impossible_date_raises(tmp_path):
    """A typo in a date prefix must not silently lose to an older fixture."""
    _touch(tmp_path, "2026-01-01-iana-tlds.json", "2026-13-45-iana-tlds.json")

    with pytest.raises(ValueError, match="2026-13-45"):
        latest_fixture(tmp_path, "iana-tlds.json")


def test_latest_fixture_resolves_the_committed_iana_tlds_fixture():
    assert latest_fixture(CORE_FIXTURES, "iana-tlds.json").is_file()
