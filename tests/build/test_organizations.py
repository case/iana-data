"""Tests for the organizations.json builder's treatment of the seed."""

import json

from src.build.organizations import build_organizations_json
from src.parse.organizations import build_resolver


def _seed(slug, display_name, **extra):
    return {
        "display_name": display_name,
        "slug": slug,
        "source_names": {},
        "aliases": [],
        "homepage": None,
        **extra,
    }


def _build(orgs, tlds, tmp_path):
    path = tmp_path / "organizations.json"
    build_organizations_json(tlds, orgs, build_resolver(orgs), path)
    return {o["slug"]: o for o in json.loads(path.read_text())["orgs"]}


def test_an_archived_only_org_keeps_its_record_and_its_archive(tmp_path):
    """M2: the archive is consumer-visible, and an archived-only org is not dropped."""
    archived = {"asn": [{"name": "GONE", "archived_on": "2026-09-12"}]}
    orgs = [_seed("ghost", "Ghost", archived=archived)]

    out = _build(orgs, [], tmp_path)

    assert out["ghost"]["archived"] == archived
    assert "roles" not in out["ghost"]


def test_an_archived_label_that_is_live_still_earns_a_role(tmp_path):
    """archived.asn resolves in the asn bucket, so attribution survives archiving."""
    orgs = [
        _seed(
            "verisign",
            "VeriSign",
            archived={"asn": [{"name": "HGTLD", "archived_on": "2026-09-12"}]},
        )
    ]
    tlds = [
        {
            "tld": "com",
            "orgs": {},
            "nameservers": [{"ipv4": [{"as_org": "HGTLD"}], "ipv6": []}],
        }
    ]

    out = _build(orgs, tlds, tmp_path)

    assert out["verisign"]["roles"]["asn"]["operator"] == ["com"]


def test_an_archived_label_earns_no_role_in_another_bucket(tmp_path):
    """The narrowing, at build level: an alias here would have matched."""
    orgs = [
        _seed(
            "acme",
            "Acme",
            archived={"asn": [{"name": "Acme Corp", "archived_on": "2026-09-12"}]},
        )
    ]
    tlds = [{"tld": "test", "orgs": {"iana": {"sponsor": "Acme Corp"}}}]

    out = _build(orgs, tlds, tmp_path)

    assert "roles" not in out["acme"]
