"""Shared one-shot build for the typed-graph integrity suites.

build_tlds_json writes the full TLD set plus every reverse-index artifact. The
session-scoped fixture runs it once into a temp dir so the places/cultures/
agreements integrity modules all read the same fresh build instead of the
committed data/generated files (which only exist after a `./bin/build`).
"""

import json
from types import SimpleNamespace

import pytest

from tests.conftest import asn_artifact_is_usable, build_into


@pytest.fixture(scope="session")
def typed_graph(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("typed_graph")
    paths = build_into(tmp, preserve_asn=not asn_artifact_is_usable())

    tlds = {e["tld"]: e for e in json.loads(paths.tlds_json.read_text())["tlds"]}
    return SimpleNamespace(
        tlds=tlds,
        places=json.loads(paths.places_json.read_text()),
        cultures=json.loads(paths.cultures_json.read_text()),
        agreements=json.loads(paths.agreements_json.read_text()),
    )
