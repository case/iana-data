"""Tests for hand-curated per-TLD annotations parsing."""

from pathlib import Path

from src.parse.manual_annotations import parse_manual_annotations

FIXTURE = Path(__file__).parent.parent / "fixtures" / "manual" / "annotations.json"


def test_parse_manual_annotations_keyed_by_tld():
    """Records are keyed by bare lowercase TLD."""
    annotations = parse_manual_annotations(FIXTURE)

    assert set(annotations) == {"amsterdam", "arab", "eus"}


def test_parse_manual_annotations_both_fields():
    """A TLD can carry both geographic_scope and cultural_affiliation."""
    annotations = parse_manual_annotations(FIXTURE)

    assert annotations["eus"] == {
        "geographic_scope": "subdivision",
        "cultural_affiliation": "basque",
    }


def test_parse_manual_annotations_single_field():
    """A TLD may carry only one annotation field."""
    annotations = parse_manual_annotations(FIXTURE)

    assert annotations["arab"] == {"cultural_affiliation": "arab"}
    assert annotations["amsterdam"] == {"geographic_scope": "city"}


def test_parse_manual_annotations_missing_file():
    """A missing file yields an empty map, not an error."""
    assert parse_manual_annotations(Path("/nonexistent/annotations.json")) == {}
