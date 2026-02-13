"""Path and text sanitization utilities for FFMPEGA.

Provides validation for file paths used in subprocess calls and
escaping for text parameters embedded in FFMPEG filter strings.
"""

import os
import re
from pathlib import Path

# Common video, image, and audio extensions
ALLOWED_EXTENSIONS = {
    # Video
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.mpg', '.mpeg', '.3gp', '.ts',
    '.m2ts', '.mts', '.vob', '.ogv',
    # Image (often used as input)
    '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff', '.heic',
    # Audio
    '.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg', '.wma', '.opus'
}

ALLOWED_SUBTITLE_EXTENSIONS = {'.srt', '.ass', '.vtt', '.sub', '.sbv', '.json'}
ALLOWED_LUT_EXTENSIONS = {'.cube', '.3dl', '.csp', '.look', '.vlt'}
ALLOWED_FONT_EXTENSIONS = {'.ttf', '.otf', '.woff', '.woff2', '.ttc'}


def validate_path(path: str, allowed_extensions: set[str], must_exist: bool = True) -> str:
    """Generic path validator for file inputs.

    Args:
        path: The path string to validate.
        allowed_extensions: Set of allowed file extensions (e.g. {'.srt', '.ass'}).
        must_exist: If True, raises ValueError when the file doesn't exist.

    Returns:
        The resolved, absolute path string.

    Raises:
        ValueError: If path is invalid, contains traversal, has invalid extension,
                    or file doesn't exist (when must_exist=True).
    """
    if not path or not path.strip():
        raise ValueError("Path cannot be empty")

    resolved = Path(path).resolve()

    # Reject paths that try to escape via traversal
    if ".." in Path(path).parts:
        raise ValueError(
            f"Path contains directory traversal (..): {path}"
        )

    if resolved.suffix.lower() not in allowed_extensions:
        raise ValueError(
            f"Invalid file extension: {resolved.suffix}. "
            f"Allowed: {sorted(list(allowed_extensions))}"
        )

    if must_exist:
        if not resolved.exists():
            raise ValueError(f"File not found: {resolved}")
        if not resolved.is_file():
            raise ValueError(f"Path is not a file: {resolved}")

    return str(resolved)


def validate_video_path(path: str, must_exist: bool = True) -> str:
    """Validate and resolve a video file path.

    Args:
        path: The path string to validate.
        must_exist: If True, raises ValueError when the file doesn't exist.

    Returns:
        The resolved, absolute path string.

    Raises:
        ValueError: If the path is empty, contains traversal sequences,
                     is not a supported file type, or doesn't exist (when must_exist is True).
    """
    return validate_path(path, ALLOWED_EXTENSIONS, must_exist=must_exist)


def validate_output_path(path: str) -> str:
    """Validate an output file or directory path.

    Resolves the path and ensures the parent directory can be created.
    Does NOT require the file to exist.

    Args:
        path: The output path string to validate.

    Returns:
        The resolved, absolute path string.

    Raises:
        ValueError: If the path is empty or contains traversal sequences.
    """
    if not path or not path.strip():
        raise ValueError("Output path cannot be empty")

    if ".." in Path(path).parts:
        raise ValueError(
            f"Output path contains directory traversal (..): {path}"
        )

    return str(Path(path).resolve())


def validate_output_file_path(path: str) -> str:
    """Validate an output file path, ensuring it has a safe extension.

    This should be used when the output path is known to be a file,
    not a directory.

    Args:
        path: The output file path string to validate.

    Returns:
        The resolved, absolute path string.

    Raises:
        ValueError: If the path is invalid, contains traversal, or has
                    a disallowed extension.
    """
    # Use validate_path with must_exist=False
    return validate_path(path, ALLOWED_EXTENSIONS, must_exist=False)


def sanitize_text_param(text: str) -> str:
    """Escape special characters in text for use in FFMPEG filter strings.

    FFMPEG's drawtext filter uses : ; ' \\ and other characters as
    delimiters.  This function escapes them so they are treated as
    literal characters.

    Args:
        text: The raw text string.

    Returns:
        Escaped text safe for use in FFMPEG filter parameters.
    """
    if not text:
        return text

    # Escape backslashes first (before adding more)
    text = text.replace("\\", "\\\\")
    # Escape FFMPEG special characters
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace(";", "\\;")
    # Escape % (used for time codes in drawtext)
    text = text.replace("%", "%%")
    # Escape comma (used for filter delimiters)
    text = text.replace(",", "\\,")

    return text


def redact_secret(secret: str, visible_chars: int = 4) -> str:
    """Redact a secret string, showing only the last few characters.

    Args:
        secret: The secret value to redact.
        visible_chars: Number of trailing characters to keep visible.

    Returns:
        Redacted string like '****abcd', or '****' if too short.
    """
    if not secret:
        return ""
    if len(secret) <= visible_chars:
        return "****"
    return "****" + secret[-visible_chars:]


def sanitize_api_key(text: str, api_key: str) -> str:
    """Remove all occurrences of an API key from a text string.

    Args:
        text: The text that may contain the API key.
        api_key: The API key to scrub.

    Returns:
        Text with all key occurrences replaced by a redacted placeholder.
    """
    if not text or not api_key:
        return text or ""
    return text.replace(api_key, redact_secret(api_key))
