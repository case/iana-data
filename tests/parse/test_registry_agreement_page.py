"""Tests for the ICANN registry agreement page renderer."""

from pathlib import Path

import pytest

from src.parse.registry_agreement_page import (
    RegistryAgreementPageError,
    extract_registry_agreements,
    render_registry_agreement_csv,
)

FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "source"
    / "icann"
    / "registry-agreements-page.html"
)

EXPECTED_CSV = (
    '\ufeff"Top Level Domain","U-Label","Translation","Agreement Type","Operator",'
    '"Agreement Status","Agreement Date","Link"\n'
    '"aaa",,,"Base, Brand (Spec 13), Non-Sponsored",'
    '"American Automobile Association, Inc.","active","26 Feb 2015",'
    '"https://www.icann.org/en/registry-agreements/details/aaa"\n'
    '"abarth",,,"Base, Brand (Spec 13), Non-Sponsored",'
    '"Fiat Chrysler Automobiles N.V.","terminated","30 Jul 2015",'
    '"https://www.icann.org/en/registry-agreements/terminated/abarth"\n'
    '"aco",,,"Base, Brand (Spec 13), Community (Spec 12), Non-Sponsored",'
    '"ACO Severin Ahlmann GmbH & Co. KG","active","8 Jan 2015",'
    '"https://www.icann.org/en/registry-agreements/details/aco"\n'
    '"asia",,,"Base, Community (Spec 12), Sponsored",'
    '"DotAsia Organisation Limited","active","30 Jun 2019",'
    '"https://www.icann.org/en/registry-agreements/details/asia"\n'
    '"gdn",,,"Base, Non-Sponsored",'
    '"Joint Stock Company ""Navigation-information systems""","active","31 Jul 2014",'
    '"https://www.icann.org/en/registry-agreements/details/gdn"\n'
    '"xn--nyqy26a","健康","healthy","Base, Non-Sponsored",'
    '"Stable Tone Limited","active","7 Nov 2014",'
    '"https://www.icann.org/en/registry-agreements/details/xn--nyqy26a"\n'
    '"zuerich",,,"Base, Non-Sponsored",'
    '"Kanton Zürich","active","7 Nov 2014",'
    '"https://www.icann.org/en/registry-agreements/details/zuerich"'
).encode()


@pytest.fixture
def page_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_render_matches_expected_csv_exactly(page_html):
    """The rendered bytes reproduce the browser's CSV, byte for byte."""
    assert render_registry_agreement_csv(page_html) == EXPECTED_CSV


def test_render_sorts_rows_by_tld(page_html):
    """Rows come out sorted by TLD regardless of upstream ordering."""
    rows = render_registry_agreement_csv(page_html).decode("utf-8").split("\n")[1:]
    tlds = [row.split(",")[0].strip('"') for row in rows]
    assert tlds == sorted(tlds)


def test_render_blanks_ulabel_when_same_as_tld(page_html):
    """An ASCII TLD whose uLabel equals the TLD gets an empty U-Label column."""
    csv_text = render_registry_agreement_csv(page_html).decode("utf-8")
    assert '"aaa",,,' in csv_text


def test_render_keeps_ulabel_and_translation_for_idn(page_html):
    """An IDN keeps both its U-label and translation."""
    csv_text = render_registry_agreement_csv(page_html).decode("utf-8")
    assert '"xn--nyqy26a","健康","healthy",' in csv_text


def test_render_uses_terminated_path_for_terminated_agreements(page_html):
    """Terminated agreements link to /terminated/, active ones to /details/."""
    csv_text = render_registry_agreement_csv(page_html).decode("utf-8")
    assert "/registry-agreements/terminated/abarth" in csv_text
    assert "/registry-agreements/details/aaa" in csv_text


def test_render_escapes_embedded_quotes(page_html):
    """Double quotes inside a field are doubled, per RFC 4180."""
    csv_text = render_registry_agreement_csv(page_html).decode("utf-8")
    assert '"Joint Stock Company ""Navigation-information systems"""' in csv_text


def test_extract_returns_all_records(page_html):
    """Every record in the embedded state is returned."""
    assert len(extract_registry_agreements(page_html)) == 7


@pytest.mark.parametrize(
    "html,reason",
    [
        ("<html><body>no state here</body></html>", "missing ng-state script"),
        (
            '<script id="ng-state" type="application/json">{not json}</script>',
            "bad JSON",
        ),
        (
            '<script id="ng-state" type="application/json">{}</script>',
            "missing key path",
        ),
        (
            (
                '<script id="ng-state" type="application/json">'
                '{"registry-agreements-{}":{"data":{"registryAgreementOperations":'
                '{"registryAgreements":[]}}}}</script>'
            ),
            "empty record list",
        ),
        (
            (
                '<script id="ng-state" type="application/json">'
                '{"registry-agreements-{}":{"data":{"registryAgreementOperations":'
                '{"registryAgreements":{}}}}}</script>'
            ),
            "records not a list",
        ),
    ],
)
def test_extract_raises_when_page_structure_changes(html, reason):
    """A site redesign fails loudly rather than yielding an empty table."""
    with pytest.raises(RegistryAgreementPageError):
        extract_registry_agreements(html)


def test_render_rejects_malformed_tld():
    """A TLD that cannot appear in a URL path is rejected, not interpolated."""
    html = (
        '<script id="ng-state" type="application/json">'
        '{"registry-agreements-{}":{"data":{"registryAgreementOperations":'
        '{"registryAgreements":[{"topLevelDomain":"../../evil","uLabel":"",'
        '"translation":null,"agreementType":"Base","operator":"x",'
        '"agreementStatus":"Active","agreementDate":"2020-01-01"}]}}}}</script>'
    )
    with pytest.raises(RegistryAgreementPageError, match="top-level domain"):
        render_registry_agreement_csv(html)


def test_render_rejects_record_missing_tld():
    """A record with no TLD is a schema change, not a row to skip."""
    html = (
        '<script id="ng-state" type="application/json">'
        '{"registry-agreements-{}":{"data":{"registryAgreementOperations":'
        '{"registryAgreements":[{"uLabel":"x","agreementStatus":"Active"}]}}}}</script>'
    )
    with pytest.raises(RegistryAgreementPageError):
        render_registry_agreement_csv(html)


def test_render_rejects_unparseable_date():
    """A date in an unexpected format fails loudly."""
    html = (
        '<script id="ng-state" type="application/json">'
        '{"registry-agreements-{}":{"data":{"registryAgreementOperations":'
        '{"registryAgreements":[{"topLevelDomain":"test","uLabel":"test",'
        '"translation":null,"agreementType":"Base","operator":"x",'
        '"agreementStatus":"Active","agreementDate":"07/11/2014"}]}}}}</script>'
    )
    with pytest.raises(RegistryAgreementPageError, match="agreement date"):
        render_registry_agreement_csv(html)


def test_render_allows_missing_optional_fields():
    """Absent optional fields render as empty columns rather than failing."""
    html = (
        '<script id="ng-state" type="application/json">'
        '{"registry-agreements-{}":{"data":{"registryAgreementOperations":'
        '{"registryAgreements":[{"topLevelDomain":"test",'
        '"agreementStatus":"Active"}]}}}}</script>'
    )
    csv_text = render_registry_agreement_csv(html).decode("utf-8")
    assert csv_text.endswith(
        '"test",,,,,"active",,'
        '"https://www.icann.org/en/registry-agreements/details/test"'
    )


def test_render_output_is_parseable_by_the_existing_csv_parser(page_html, tmp_path):
    """The rendered file round-trips through the parser that consumes it."""
    from src.parse.registry_agreement_csv import parse_registry_agreement_csv

    path = tmp_path / "table.csv"
    path.write_bytes(render_registry_agreement_csv(page_html))
    agreements = parse_registry_agreement_csv(path)

    assert set(agreements) == {
        "aaa",
        "abarth",
        "aco",
        "asia",
        "gdn",
        "xn--nyqy26a",
        "zuerich",
    }
    assert agreements["aco"]["agreement_types"] == [
        "Base",
        "Brand (Spec 13)",
        "Community (Spec 12)",
        "Non-Sponsored",
    ]
    assert agreements["abarth"]["status"] == "terminated"
    assert agreements["xn--nyqy26a"].get("u_label") == "健康"
    assert "u_label" not in agreements["aaa"]


def test_render_rejects_unknown_agreement_type():
    """A new upstream agreement type breaks byte fidelity, so it fails loudly."""
    html = (
        '<script id="ng-state" type="application/json">'
        '{"registry-agreements-{}":{"data":{"registryAgreementOperations":'
        '{"registryAgreements":[{"topLevelDomain":"test",'
        '"agreementType":"Base, Brand New Category",'
        '"agreementStatus":"Active","agreementDate":"2020-01-01"}]}}}}</script>'
    )
    with pytest.raises(RegistryAgreementPageError, match="unknown agreement type"):
        render_registry_agreement_csv(html)


def test_agreement_type_order_matches_the_config_mapping():
    """The two lists are one list; a new ICANN type cannot be added to only one."""
    from src.config import REGISTRY_AGREEMENT_TYPE_MAPPING
    from src.parse.registry_agreement_page import AGREEMENT_TYPE_ORDER

    assert AGREEMENT_TYPE_ORDER == tuple(REGISTRY_AGREEMENT_TYPE_MAPPING)
