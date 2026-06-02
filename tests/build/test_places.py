"""Integration tests for the places build (data/generated/places.json)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _pytest.monkeypatch import MonkeyPatch

from src.build.places import (
    _build_countries,
    _manual_records,
    _ordered_place,
    _overlay_country_coordinates,
)
from src.build.tlds import OutputPaths, build_tlds_json


@pytest.fixture(scope="module")
def places(tmp_path_factory):
    """Build all outputs once and return the parsed places.json records by slug."""
    tmp = tmp_path_factory.mktemp("places_build")
    mp = MonkeyPatch()
    mp.setattr("src.utilities.metadata.METADATA_FILE", str(tmp / "metadata.json"))
    paths = OutputPaths(
        tlds_json=tmp / "tlds.json",
        tlds_index=tmp / "tlds-index.json",
        tld_dir=tmp / "tld",
        organizations_json=tmp / "organizations.json",
        places_json=tmp / "places.json",
        cultures_json=tmp / "cultures.json",
        agreements_json=tmp / "agreements.json",
    )
    build_tlds_json(paths)
    data = json.loads(Path(paths.places_json).read_text(encoding="utf-8"))
    by_slug = {rec["slug"]: rec for rec in data["places"]}
    yield SimpleNamespace(by_slug=by_slug)
    mp.undo()


def test_country_carries_iso_numeric(places):
    assert places.by_slug["za"]["iso_numeric"] == "710"


def test_iso_numeric_preserves_zero_padding(places):
    # Afghanistan is "004", not "4". Guards against casting the code to int,
    # which would silently break joins against zero-padded geometry ids.
    assert places.by_slug["af"]["iso_numeric"] == "004"


def test_iso_numeric_is_string_when_present(places):
    assert isinstance(places.by_slug["za"]["iso_numeric"], str)


@pytest.mark.parametrize("slug", ["ac", "su"])
def test_non_iso_cctld_has_null_iso_numeric(places, slug):
    # ac (Ascension) and su (Soviet Union) are reserved ccTLDs with no ISO
    # 3166-1 alpha-2 assignment, hence no numeric code.
    assert slug in places.by_slug
    assert places.by_slug[slug]["iso_numeric"] is None


def _city(**overrides) -> dict:
    rec = {
        "subtype": "city",
        "name_en": "Durban",
        "iso_code": None,
        "parent": "za",
        "info_link": "https://en.wikipedia.org/wiki/Durban",
        "tlds": ["durban"],
    }
    rec.update(overrides)
    return rec


def test_manual_records_carries_coordinates_when_present():
    coords = {"lat": -29.8583, "lon": 31.025}
    out = _manual_records({"durban": _city(coordinates=coords)})
    assert out[0]["coordinates"] == coords


def test_manual_records_omits_coordinates_when_absent():
    out = _manual_records(
        {
            "alsace": {
                "subtype": "subdivision",
                "name_en": "Alsace",
                "iso_code": None,
                "parent": "fr",
                "info_link": "https://en.wikipedia.org/wiki/Alsace",
                "tlds": ["alsace"],
            }
        }
    )
    assert "coordinates" not in out[0]


def test_overlay_country_coordinates_adds_fields_without_touching_identity():
    countries = {"cc": {"slug": "cc", "subtype": "country", "iso_numeric": "166"}}
    overlay = {
        "cc": {
            "info_link": "https://en.wikipedia.org/wiki/Cocos_(Keeling)_Islands",
            "coordinates": {"lat": -12.17, "lon": 96.83},
        }
    }
    _overlay_country_coordinates(countries, overlay)
    assert countries["cc"]["coordinates"] == {"lat": -12.17, "lon": 96.83}
    assert countries["cc"]["info_link"].endswith("Cocos_(Keeling)_Islands")
    assert countries["cc"]["iso_numeric"] == "166"  # identity stays derived


def test_build_countries_folds_gtld_into_its_country():
    # A delegated gTLD in gtld_country joins the country's record (swiss -> ch),
    # alongside the ccTLD, with no standalone record of its own.
    tlds = [{"tld": "ch", "delegated": True}, {"tld": "swiss", "delegated": True}]
    countries = _build_countries(tlds, set(), {"swiss": "ch"}, {})
    assert sorted(countries["ch"]["tlds"]) == ["ch", "swiss"]
    assert "swiss" not in countries


def test_build_countries_skips_unknown_fold_target(caplog):
    # A fold target that is not an ISO country is logged and skipped, never
    # fabricated into a junk country record. The same case is a hard failure via
    # test_places_integrity.test_fold_into_country_consistent_and_resolves.
    tlds = [{"tld": "swiss", "delegated": True}]
    with caplog.at_level("WARNING"):
        countries = _build_countries(tlds, set(), {"swiss": "zz"}, {})
    assert "zz" not in countries
    assert "swiss" not in countries
    assert "swiss" in caplog.text


def test_overlay_country_coordinates_skips_unknown_slug(caplog):
    countries: dict[str, dict] = {}
    with caplog.at_level("WARNING"):
        _overlay_country_coordinates(
            countries, {"zz": {"coordinates": {"lat": 1.0, "lon": 2.0}}}
        )
    assert countries == {}
    assert "zz" in caplog.text  # the skip is logged, not silent


def test_ordered_place_sorts_fields_alphabetically():
    out = _ordered_place({"tlds": ["cc"], "slug": "cc", "iso_numeric": "166"})
    assert list(out) == ["iso_numeric", "slug", "tlds"]


def test_no_polygon_territory_keeps_iso_numeric_and_gets_overlay(places):
    # cc (Cocos) has no 50m polygon, so it carries a point overlay. Its identity
    # (iso_numeric) must stay pycountry-derived, and the overlay info_link applies.
    cc = places.by_slug["cc"]
    assert cc["iso_numeric"] == "166"
    assert cc["info_link"].endswith("Cocos_(Keeling)_Islands")


def test_place_records_have_alphabetical_fields(places):
    # One consistent field order across every record type, applied at build time.
    for rec in (places.by_slug["za"], places.by_slug["cc"], places.by_slug["durban"]):
        assert list(rec) == sorted(rec)
