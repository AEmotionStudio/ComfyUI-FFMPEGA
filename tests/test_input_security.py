
import pytest
from pathlib import Path
from core.sanitize import validate_path

def test_sensitive_input_path_blocked(tmp_path):
    # Setup a sensitive directory structure in a temporary location
    sensitive_dir = tmp_path / ".ssh"
    sensitive_dir.mkdir()
    sensitive_file = sensitive_dir / "id_rsa.png" # Using a valid extension
    sensitive_file.write_text("fake key")

    # Attempt to validate a path inside the sensitive directory
    with pytest.raises(ValueError, match="Path contains sensitive directory: .ssh"):
        validate_path(str(sensitive_file), allowed_extensions={'.png'})

def test_safe_input_path_allowed(tmp_path):
    # Setup a safe file
    safe_file = tmp_path / "video.mp4"
    safe_file.write_text("fake video content")

    # Should not raise exception
    validated = validate_path(str(safe_file), allowed_extensions={'.mp4'})
    assert Path(validated) == safe_file.resolve()

def test_input_path_traversal_blocked(tmp_path):
    # Setup a file
    target_file = tmp_path / "image.jpg"
    target_file.write_text("fake image")

    # Attempt traversal
    traversal_path = str(tmp_path / "subdir" / ".." / "image.jpg")

    # validate_path explicitly checks for ".." in parts
    with pytest.raises(ValueError, match="Path contains directory traversal"):
        validate_path(traversal_path, allowed_extensions={'.jpg'})
