"""Tests for TLD file parsing."""

from pathlib import Path

from src.parse.tlds_txt import parse_tlds_file, tlds_txt_content_changed

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "source"


def test_parse_tlds_file_ignores_comments_and_empty_lines():
    """Test that parse_tlds_file correctly filters comments and empty lines."""
    fixture_path = FIXTURES_DIR / "tlds.txt"
    content = fixture_path.read_text()

    tlds = parse_tlds_file(content)

    # Should have 22 TLDs (not counting the comment line or empty lines)
    assert len(tlds) == 22

    # Should not contain any comments
    assert all(not tld.startswith("#") for tld in tlds)

    # Should contain expected TLDs (in original uppercase)
    assert "AAA" in tlds
    assert "AARP" in tlds
    assert "XN--WGBH1C" in tlds


def test_parse_tlds_file_timestamp_only_change():
    """Test that files with only timestamp changes parse to same TLD list."""
    baseline_path = FIXTURES_DIR / "tlds.txt"
    timestamp_only_path = FIXTURES_DIR / "tlds-timestamp-only.txt"

    baseline_content = baseline_path.read_text()
    timestamp_only_content = timestamp_only_path.read_text()

    baseline_tlds = parse_tlds_file(baseline_content)
    timestamp_only_tlds = parse_tlds_file(timestamp_only_content)

    # Should have same TLDs despite different timestamps
    assert baseline_tlds == timestamp_only_tlds


def test_parse_tlds_file_content_change():
    """Test that files with actual content changes parse to different TLD lists."""
    baseline_path = FIXTURES_DIR / "tlds.txt"
    new_content_path = FIXTURES_DIR / "tlds-new-content.txt"

    baseline_content = baseline_path.read_text()
    new_content = new_content_path.read_text()

    baseline_tlds = parse_tlds_file(baseline_content)
    new_tlds = parse_tlds_file(new_content)

    # Should have different TLDs
    assert baseline_tlds != new_tlds

    # New content should have one more TLD
    assert len(new_tlds) == len(baseline_tlds) + 1

    # New content should have "HELLO"
    assert "HELLO" in new_tlds
    assert "HELLO" not in baseline_tlds


def test_tlds_txt_content_changed_timestamp_only(tmp_path):
    """Test that timestamp-only changes are detected as not changed."""
    # Create a temporary existing file
    existing_file = tmp_path / "tlds.txt"
    baseline_path = FIXTURES_DIR / "tlds.txt"
    existing_file.write_text(baseline_path.read_text())

    # Load timestamp-only change content
    timestamp_only_path = FIXTURES_DIR / "tlds-timestamp-only.txt"
    new_content = timestamp_only_path.read_text()

    # Should return False (content hasn't changed)
    assert not tlds_txt_content_changed(existing_file, new_content)


def test_tlds_txt_content_changed_actual_change(tmp_path):
    """Test that actual content changes are detected."""
    # Create a temporary existing file
    existing_file = tmp_path / "tlds.txt"
    baseline_path = FIXTURES_DIR / "tlds.txt"
    existing_file.write_text(baseline_path.read_text())

    # Load new content with actual changes
    new_content_path = FIXTURES_DIR / "tlds-new-content.txt"
    new_content = new_content_path.read_text()

    # Should return True (content has changed)
    assert tlds_txt_content_changed(existing_file, new_content)


def test_tlds_txt_content_changed_file_does_not_exist(tmp_path):
    """Test that non-existent files are considered changed."""
    non_existent_file = tmp_path / "does-not-exist.txt"
    new_content = "# Comment\nAAA\nBBB\n"

    # Should return True (file doesn't exist, so it's a change)
    assert tlds_txt_content_changed(non_existent_file, new_content)
