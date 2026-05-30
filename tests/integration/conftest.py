"""Shared one-shot build for the typed-graph integrity suites.

build_tlds_json writes the full TLD set plus every reverse-index artifact. The
session-scoped fixture runs it once into a temp dir so the places/cultures/
agreements integrity modules all read the same fresh build instead of the
committed data/generated files (which only exist after a `./bin/build`).
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.build.tlds import OutputPaths, build_tlds_json


@pytest.fixture(scope="session")
def typed_graph(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("typed_graph")
    with patch("src.utilities.metadata.METADATA_FILE", str(tmp / "metadata.json")):
        paths = OutputPaths(
            tlds_json=tmp / "tlds.json",
            tlds_index=tmp / "tlds-index.json",
            tld_dir=tmp / "tld",
            organizations_json=tmp / "organizations.json",
            places_json=tmp / "places.json",
            cultures_json=tmp / "cultures.json",
            agreements_json=tmp / "agreements.json",
        )
        result = build_tlds_json(paths)
    assert not result.get("error"), result.get("error")

    tlds = {e["tld"]: e for e in json.loads(paths.tlds_json.read_text())["tlds"]}
    return SimpleNamespace(
        tlds=tlds,
        places=json.loads(paths.places_json.read_text()),
        cultures=json.loads(paths.cultures_json.read_text()),
        agreements=json.loads(paths.agreements_json.read_text()),
    )
