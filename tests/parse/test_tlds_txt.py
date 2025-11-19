"""Tests for TLD file parsing."""

from pathlib import Path

from src.parse.tlds_txt import _parse_tlds_content, parse_tlds_txt, tlds_txt_content_changed

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


def test_parse_tlds_content_ignores_comments_and_empty_lines():
    """Test that _parse_tlds_content correctly filters comments and empty lines."""
    fixture_path = FIXTURES_DIR / "tlds.txt"
    content = fixture_path.read_text()

    tlds = _parse_tlds_content(content)

    # Should have 22 TLDs (not counting the comment line or empty lines)
    assert len(tlds) == 22

    # Should not contain any comments
    assert all(not tld.startswith("#") for tld in tlds)

    # Should contain expected TLDs (in original uppercase)
    assert "AAA" in tlds
    assert "AARP" in tlds
    assert "XN--WGBH1C" in tlds


def test_parse_tlds_content_timestamp_only_change():
    """Test that files with only timestamp changes parse to same TLD list."""
    baseline_path = FIXTURES_DIR / "tlds.txt"
    timestamp_only_path = FIXTURES_DIR / "tlds-timestamp-only.txt"

    baseline_content = baseline_path.read_text()
    timestamp_only_content = timestamp_only_path.read_text()

    baseline_tlds = _parse_tlds_content(baseline_content)
    timestamp_only_tlds = _parse_tlds_content(timestamp_only_content)

    # Should have same TLDs despite different timestamps
    assert baseline_tlds == timestamp_only_tlds


def test_parse_tlds_content_content_change():
    """Test that files with actual content changes parse to different TLD lists."""
    baseline_path = FIXTURES_DIR / "tlds.txt"
    new_content_path = FIXTURES_DIR / "tlds-new-content.txt"

    baseline_content = baseline_path.read_text()
    new_content = new_content_path.read_text()

    baseline_tlds = _parse_tlds_content(baseline_content)
    new_tlds = _parse_tlds_content(new_content)

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


def test_parse_tlds_txt_with_filepath():
    """Test that parse_tlds_txt correctly parses a file from filepath."""
    fixture_path = FIXTURES_DIR / "tlds.txt"

    tlds = parse_tlds_txt(fixture_path)

    # Should have 22 TLDs (not counting the comment line or empty lines)
    assert len(tlds) == 22

    # Should not contain any comments
    assert all(not tld.startswith("#") for tld in tlds)

    # Should contain expected TLDs (normalized to lowercase by default)
    assert "aaa" in tlds
    assert "aarp" in tlds
    assert "xn--wgbh1c" in tlds


def test_parse_tlds_txt_without_normalize():
    """Test that parse_tlds_txt preserves original case when normalize=False."""
    fixture_path = FIXTURES_DIR / "tlds.txt"

    tlds = parse_tlds_txt(fixture_path, normalize=False)

    # Should have 22 TLDs
    assert len(tlds) == 22

    # Should contain TLDs in original uppercase
    assert "AAA" in tlds
    assert "AARP" in tlds
    assert "XN--WGBH1C" in tlds

    # Lowercase versions should NOT be present
    assert "aaa" not in tlds


def test_parse_tlds_txt_with_default_path():
    """Test that parse_tlds_txt uses default path when none provided."""
    # This should use the default path from config
    # We can't test the exact output without knowing what's in the file,
    # but we can verify it returns a list
    tlds = parse_tlds_txt()

    assert isinstance(tlds, list)


def test_parse_tlds_txt_missing_file(tmp_path):
    """Test that parse_tlds_txt handles missing file gracefully."""
    non_existent_file = tmp_path / "does-not-exist.txt"

    tlds = parse_tlds_txt(non_existent_file)

    # Should return empty list on error
    assert tlds == []
