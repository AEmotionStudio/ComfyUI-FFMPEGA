
import pytest
from pathlib import Path
from core.sanitize import validate_output_path, sanitize_text_param

def test_sensitive_dir_traversal_blocked():
    # Test path inside a sensitive directory like .ssh
    # We use a path that might look valid otherwise
    sensitive_path = "/home/user/.ssh/id_rsa.pub"

    with pytest.raises(ValueError, match="Path contains sensitive directory: .ssh"):
        validate_output_path(sensitive_path)

    # Test path with .git
    git_path = "./.git/config"
    with pytest.raises(ValueError, match="Path contains sensitive directory: .git"):
        validate_output_path(git_path)

    # Test path with .env
    env_path = "/app/.env"
    with pytest.raises(ValueError, match="Path contains sensitive directory: .env"):
        validate_output_path(env_path)

def test_safe_path_allowed():
    # Test a safe path
    safe_path = "/tmp/video.mp4"
    # Compare resolved paths to handle symlinks/absolute path differences
    assert Path(validate_output_path(safe_path)) == Path(safe_path).resolve()

    # Test a path with safe hidden dir (not in sensitive list)
    # E.g. .cache is not in SENSITIVE_DIRS
    hidden_safe = "/home/user/.cache/video.mp4"
    # Note: .cache is NOT in SENSITIVE_DIRS currently
    assert Path(validate_output_path(hidden_safe)) == Path(hidden_safe).resolve()

def test_null_byte_rejection():
    # Test null byte in text param
    with pytest.raises(ValueError, match="Null byte found in text parameter"):
        sanitize_text_param("hello\0world")

    # Test valid text - spaces are NOT escaped by sanitize_text_param
    assert sanitize_text_param("hello world") == "hello world"
    # Special chars are escaped
    assert sanitize_text_param("hello, world") == "hello\\, world"

def test_sensitive_dirs_in_unsafe_list():
    # Verify we didn't break UNSAFE_DIRECTORIES check
    with pytest.raises(ValueError, match="Path targets unsafe system directory"):
        validate_output_path("/etc/passwd")

    with pytest.raises(ValueError, match="Path targets unsafe system directory"):
        validate_output_path("/opt/app/config.json")
