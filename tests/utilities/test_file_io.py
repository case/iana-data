"""Tests for centralized file I/O utilities."""

from pathlib import Path

from src.utilities.file_io import read_json_file, read_text_file

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


def test_read_json_file_success():
    """Test successful JSON file reading."""
    filepath = FIXTURES_DIR / "rdap.json"
    data = read_json_file(filepath)

    assert isinstance(data, dict)
    assert "services" in data
    assert "publication" in data


def test_read_json_file_missing_file():
    """Test reading non-existent JSON file returns default."""
    filepath = Path("/nonexistent/file.json")
    data = read_json_file(filepath)

    assert data == {}


def test_read_json_file_missing_file_with_custom_default():
    """Test reading non-existent JSON file returns custom default."""
    filepath = Path("/nonexistent/file.json")
    data = read_json_file(filepath, default=[])

    assert data == []


def test_read_json_file_corrupted_json(tmp_path):
    """Test reading corrupted JSON file returns default."""
    filepath = tmp_path / "corrupted.json"
    filepath.write_text("{ invalid json here }")

    data = read_json_file(filepath)

    assert data == {}


def test_read_json_file_corrupted_json_with_custom_default(tmp_path):
    """Test reading corrupted JSON file returns custom default."""
    filepath = tmp_path / "corrupted.json"
    filepath.write_text("{ invalid json here }")

    data = read_json_file(filepath, default={"error": True})

    assert data == {"error": True}


def test_read_json_file_permission_error(tmp_path, monkeypatch):
    """Test handling of permission errors when reading JSON file."""
    filepath = tmp_path / "test.json"
    filepath.write_text('{"test": "data"}')

    # Mock read_text to raise PermissionError
    from pathlib import Path

    original_read_text = Path.read_text

    def mock_read_text(self, *args, **kwargs):
        if "test.json" in str(self):
            raise PermissionError("Permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mock_read_text)

    data = read_json_file(filepath)

    assert data == {}


def test_read_text_file_success():
    """Test successful text file reading."""
    filepath = FIXTURES_DIR / "tlds.txt"
    content = read_text_file(filepath)

    assert isinstance(content, str)
    assert len(content) > 0
    assert "# Version" in content


def test_read_text_file_missing_file():
    """Test reading non-existent text file returns default."""
    filepath = Path("/nonexistent/file.txt")
    content = read_text_file(filepath)

    assert content == ""


def test_read_text_file_missing_file_with_custom_default():
    """Test reading non-existent text file returns custom default."""
    filepath = Path("/nonexistent/file.txt")
    content = read_text_file(filepath, default="ERROR")

    assert content == "ERROR"


def test_read_text_file_permission_error(tmp_path, monkeypatch):
    """Test handling of permission errors when reading text file."""
    filepath = tmp_path / "test.txt"
    filepath.write_text("test content")

    # Mock read_text to raise PermissionError
    from pathlib import Path

    original_read_text = Path.read_text

    def mock_read_text(self, *args, **kwargs):
        if "test.txt" in str(self):
            raise PermissionError("Permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mock_read_text)

    content = read_text_file(filepath)

    assert content == ""


def test_read_text_file_permission_error_with_custom_default(tmp_path, monkeypatch):
    """Test handling of permission errors with custom default."""
    filepath = tmp_path / "test.txt"
    filepath.write_text("test content")

    # Mock read_text to raise PermissionError
    from pathlib import Path

    original_read_text = Path.read_text

    def mock_read_text(self, *args, **kwargs):
        if "test.txt" in str(self):
            raise PermissionError("Permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mock_read_text)

    content = read_text_file(filepath, default="FAILED")

    assert content == "FAILED"
