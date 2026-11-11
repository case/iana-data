"""Tests for scripts/idn_unicode_scripts/generate_idn_script_mapping.py.

scripts/ is not an importable package, so the script is loaded by path.
"""

import importlib.util
import json
from pathlib import Path

from src.parse.iana_tlds_json import IanaTldsError, parse_iana_tlds
from tests.iana_tlds_documents import document, domain, not_delegated

_SCRIPT = (
    Path(__file__).parent.parent
    / "scripts"
    / "idn_unicode_scripts"
    / "generate_idn_script_mapping.py"
)
_spec = importlib.util.spec_from_file_location("generate_idn_script_mapping", _SCRIPT)
assert _spec is not None and _spec.loader is not None
generator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generator)


def test_main_maps_every_idn_in_the_iana_tld_json(tmp_path, monkeypatch):
    """Delegated and undelegated IDNs are both mapped; ASCII names are not."""
    records = parse_iana_tlds(
        document(
            domain(name="com"),
            domain(name="xn--kpry57d", ulabel="台灣"),
            not_delegated("retired", name="xn--0zwm56d", ulabel="测试", type="test"),
        )
    )
    output = tmp_path / "idn-script-mapping.json"
    monkeypatch.setattr(generator, "load_iana_tlds", lambda: records)
    monkeypatch.setattr(generator, "IDN_SCRIPT_MAPPING_FILE", str(output))

    assert generator.main() == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "xn--kpry57d": "Han-CJK",
        "xn--0zwm56d": "Han-CJK",
    }


def test_main_fails_without_writing_when_the_json_is_unreadable(tmp_path, monkeypatch):
    output = tmp_path / "idn-script-mapping.json"

    def unreadable():
        raise IanaTldsError("domains is empty")

    monkeypatch.setattr(generator, "load_iana_tlds", unreadable)
    monkeypatch.setattr(generator, "IDN_SCRIPT_MAPPING_FILE", str(output))

    assert generator.main() == 1
    assert not output.exists()
