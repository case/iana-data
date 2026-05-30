"""Integration tests for the places build (data/generated/places.json)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _pytest.monkeypatch import MonkeyPatch

from src.build.places import _manual_records
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
