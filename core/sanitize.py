"""Path and text sanitization utilities for FFMPEGA.

Provides validation for file paths used in subprocess calls and
escaping for text parameters embedded in FFMPEG filter strings.
"""

import os
import re
from pathlib import Path


def validate_video_path(path: str, must_exist: bool = True) -> str:
    """Validate and resolve a video file path.

    Args:
        path: The path string to validate.
        must_exist: If True, raises ValueError when the file doesn't exist.

    Returns:
        The resolved, absolute path string.

    Raises:
        ValueError: If the path is empty, contains traversal sequences,
                     or doesn't exist (when must_exist is True).
    """
    if not path or not path.strip():
        raise ValueError("Path cannot be empty")

    resolved = Path(path).resolve()

    # Reject paths that try to escape via traversal
    if ".." in Path(path).parts:
        raise ValueError(
            f"Path contains directory traversal (..): {path}"
        )

    if must_exist and not resolved.exists():
        raise ValueError(f"File not found: {resolved}")

    if must_exist and not resolved.is_file():
        raise ValueError(f"Path is not a file: {resolved}")

    return str(resolved)


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

    return text
