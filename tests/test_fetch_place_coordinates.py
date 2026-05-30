"""Tests for scripts/fetch_place_coordinates.py.

scripts/ is not an importable package, so load the script by path. main() is
guarded by ``__main__``; importing only adjusts sys.path and pulls helpers.
"""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "fetch_place_coordinates.py"
_spec = importlib.util.spec_from_file_location("fetch_place_coordinates", _SCRIPT)
assert _spec is not None and _spec.loader is not None
fpc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fpc)


# --- enwiki_title_from_url ---


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://en.wikipedia.org/wiki/Durban", "Durban"),
        ("https://en.wikipedia.org/wiki/Abu_Dhabi", "Abu Dhabi"),
        ("https://en.wikipedia.org/wiki/S%C3%A3o_Paulo", "São Paulo"),
        ("https://en.wikipedia.org/wiki/Durban/", "Durban"),
        ("https://en.wikipedia.org/wiki/Durban#Climate", "Durban"),
        ("https://en.wikipedia.org/wiki/Durban?action=edit", "Durban"),
    ],
)
def test_enwiki_title_from_url_parses(url, expected):
    assert fpc.enwiki_title_from_url(url) == expected


def test_enwiki_title_from_url_returns_none_without_marker():
    assert fpc.enwiki_title_from_url("https://example.com/Durban") is None
    assert fpc.enwiki_title_from_url("") is None


# --- parse_coordinate_claim ---


def _entity(lat, lon):
    return {
        "claims": {
            "P625": [
                {
                    "mainsnak": {
                        "datavalue": {"value": {"latitude": lat, "longitude": lon}}
                    }
                }
            ]
        }
    }


def test_parse_coordinate_claim_valid():
    assert fpc.parse_coordinate_claim(_entity(-29.8583, 31.025)) == (-29.8583, 31.025)


def test_parse_coordinate_claim_missing_p625_raises():
    with pytest.raises(ValueError):
        fpc.parse_coordinate_claim({"claims": {}})


def test_parse_coordinate_claim_empty_claim_list_raises():
    with pytest.raises(ValueError):
        fpc.parse_coordinate_claim({"claims": {"P625": []}})


@pytest.mark.parametrize("lat,lon", [(91.0, 0.0), (0.0, 181.0), (-91.0, 0.0)])
def test_parse_coordinate_claim_out_of_range_raises(lat, lon):
    with pytest.raises(ValueError):
        fpc.parse_coordinate_claim(_entity(lat, lon))


def test_parse_coordinate_claim_non_numeric_raises():
    with pytest.raises(ValueError):
        fpc.parse_coordinate_claim(_entity("north", "east"))


# --- fetch_coordinates (MockTransport, no live network) ---


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_coordinates_returns_parsed_pair():
    def handler(request):
        return httpx.Response(
            200, json={"entities": {"Q5468": _entity(-29.8583, 31.025)}}
        )

    with _client(handler) as client:
        assert fpc.fetch_coordinates(client, "Durban") == (-29.8583, 31.025)


def test_fetch_coordinates_raises_on_http_error():
    def handler(request):
        return httpx.Response(404, json={})

    with _client(handler) as client:
        with pytest.raises(ValueError):
            fpc.fetch_coordinates(client, "Nowhere")


def test_fetch_coordinates_raises_on_missing_entity():
    def handler(request):
        return httpx.Response(200, json={"entities": {}})

    with _client(handler) as client:
        with pytest.raises(ValueError):
            fpc.fetch_coordinates(client, "Nowhere")


# --- enrich_places ---


def _places():
    return {
        "durban": {
            "subtype": "city",
            "info_link": "https://en.wikipedia.org/wiki/Durban",
            "tlds": ["durban"],
        },
        "alsace": {
            "subtype": "subdivision",
            "info_link": "https://en.wikipedia.org/wiki/Alsace",
            "tlds": ["alsace"],
        },
        "eu": {
            "subtype": "supranational",
            "info_link": "https://en.wikipedia.org/wiki/European_Union",
            "tlds": ["eu"],
        },
        "kyoto": {
            "subtype": "city",
            "info_link": "https://en.wikipedia.org/wiki/Kyoto",
            "tlds": ["kyoto"],
            "coordinates": {"lat": 35.0, "lon": 135.0},
        },
    }


def _coords_handler(request):
    return httpx.Response(
        200, json={"entities": {"Q1": _entity(1.23456789, 2.3456789)}}
    )


def test_enrich_places_adds_coords_to_all_geo_subtypes():
    places = _places()
    with _client(_coords_handler) as client:
        added, failed = fpc.enrich_places(places, client, refresh=False, delay=0)
    # city + subdivision + supranational all get coords; kyoto already has them.
    assert added == 3
    assert failed == []
    expected = round(1.23456789, fpc.COORD_PRECISION)
    for slug in ("durban", "alsace", "eu"):
        assert places[slug]["coordinates"]["lat"] == expected
    assert places["kyoto"]["coordinates"]["lat"] == 35.0  # untouched


def test_enrich_places_refresh_reprocesses_populated():
    places = _places()
    with _client(_coords_handler) as client:
        added, _ = fpc.enrich_places(places, client, refresh=True, delay=0)
    assert added == 4  # all four, including the already-populated kyoto
    assert places["kyoto"]["coordinates"]["lat"] == round(
        1.23456789, fpc.COORD_PRECISION
    )


def test_enrich_places_records_failures_without_writing_coords():
    places = {
        "durban": {
            "subtype": "city",
            "info_link": "https://en.wikipedia.org/wiki/Durban",
            "tlds": ["durban"],
        }
    }

    def handler(request):
        return httpx.Response(200, json={"entities": {"Q1": {"claims": {}}}})

    with _client(handler) as client:
        added, failed = fpc.enrich_places(places, client, refresh=False, delay=0)
    assert added == 0
    assert failed == ["durban"]
    assert "coordinates" not in places["durban"]


def test_enrich_places_skips_place_without_info_link():
    places = {"x": {"subtype": "subdivision", "tlds": ["x"]}}  # no info_link
    with _client(_coords_handler) as client:
        added, failed = fpc.enrich_places(places, client, refresh=False, delay=0)
    assert added == 0
    assert failed == ["x"]


def test_main_populates_places_file(tmp_path, monkeypatch):
    places_file = tmp_path / "places.json"
    places_file.write_text(
        json.dumps(
            {
                "durban": {
                    "subtype": "city",
                    "name_en": "Durban",
                    "iso_code": None,
                    "parent": "za",
                    "info_link": "https://en.wikipedia.org/wiki/Durban",
                    "tlds": ["durban"],
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fpc, "MANUAL_DIR", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["fetch_place_coordinates.py"])
    # Stub the network boundary; main()'s job is read -> enrich -> write.
    monkeypatch.setattr(
        fpc, "fetch_coordinates", lambda client, title: (-29.8583, 31.025)
    )

    rc = fpc.main()

    assert rc == 0
    data = json.loads(places_file.read_text(encoding="utf-8"))
    assert data["durban"]["coordinates"] == {"lat": -29.8583, "lon": 31.025}
