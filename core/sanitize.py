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

ALLOWED_SUBTITLE_EXTENSIONS = {'.srt', '.ass', '.vtt', '.sub', '.sbv'}
ALLOWED_LUT_EXTENSIONS = {'.cube', '.3dl', '.csp', '.look', '.vlt'}
ALLOWED_FONT_EXTENSIONS = {'.ttf', '.otf', '.woff', '.woff2', '.ttc'}

# Critical system directories that should be protected from write operations
UNSAFE_DIRECTORIES = {
    "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc",
    "/root", "/run", "/sbin", "/sys", "/usr", "/var", "/opt", "/srv"
}

# Sensitive directories that should not be part of any output path
SENSITIVE_DIRS = {
    ".ssh", ".aws", ".kube", ".git", ".github", ".vscode", ".idea",
    ".env", ".config"
}


def _check_unsafe_path(path: Path) -> None:
    """Check if the path targets a sensitive system directory.

    Args:
        path: The resolved path to check.

    Raises:
        ValueError: If path is unsafe.
    """
    path_str = str(path)
    # Check POSIX system paths
    for unsafe in UNSAFE_DIRECTORIES:
        # Match directory exactly or as a parent
        if path_str == unsafe or path_str.startswith(f"{unsafe}{os.sep}"):
            raise ValueError(f"Path targets unsafe system directory: {path}")

    # Check for sensitive directories in the path components
    # This prevents writing to hidden sensitive dirs like ~/.ssh/ even
    # if they are inside a allowed user directory.
    parts = path.parts
    for part in parts:
        if part in SENSITIVE_DIRS:
            raise ValueError(f"Path contains sensitive directory: {part}")

    # Check Windows system paths
    if os.name == 'nt':
        lower_path = path_str.lower()
        if (lower_path.startswith("c:\\windows") or
                lower_path.startswith("c:\\program files") or
                lower_path.startswith("c:\\program files (x86)")):
            raise ValueError(f"Path targets unsafe system directory: {path}")


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
    Does NOT require the file to exist. Also blocks writes to critical
    system directories.

    Args:
        path: The output path string to validate.

    Returns:
        The resolved, absolute path string.

    Raises:
        ValueError: If the path is empty, contains traversal sequences,
                    or targets a protected system directory.
    """
    if not path or not path.strip():
        raise ValueError("Output path cannot be empty")

    if ".." in Path(path).parts:
        raise ValueError(
            f"Output path contains directory traversal (..): {path}"
        )

    resolved = Path(path).resolve()
    _check_unsafe_path(resolved)

    return str(resolved)


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
    # Pre-check: file must have an extension
    resolved = Path(path).resolve()
    if not resolved.suffix:
        raise ValueError(
            f"Output file path must have an extension: {path}"
        )
    # Pre-check: provide output-specific error message for disallowed extensions
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Invalid output file extension: {resolved.suffix}. "
            f"Allowed: {sorted(list(ALLOWED_EXTENSIONS))}"
        )

    _check_unsafe_path(resolved)

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

    if "\0" in text:
        raise ValueError("Null byte found in text parameter")

    # Optimization: check for special chars before replacing to avoid
    # unnecessary string allocations in the common case (clean text).
    # Escape backslashes first (before adding more)
    if "\\" in text:
        text = text.replace("\\", "\\\\")
    if "'" in text:
        text = text.replace("'", "\\'")
    if ":" in text:
        text = text.replace(":", "\\:")
    if ";" in text:
        text = text.replace(";", "\\;")
    # Escape % (used for time codes in drawtext)
    if "%" in text:
        text = text.replace("%", "%%")
    # Escape comma (used for filter delimiters)
    if "," in text:
        text = text.replace(",", "\\,")
    # Escape brackets (used for stream specifiers)
    if "[" in text:
        text = text.replace("[", "\\[")
    if "]" in text:
        text = text.replace("]", "\\]")

    return text


def ffmpeg_escape_path(s: str) -> str:
    """Escape special characters in a file path for ffmpeg filter options.

    This is needed when embedding paths inside filter strings like
    ``ass=/path/to/file.ass`` where colons, commas, spaces, and other
    characters have syntactic meaning.

    Args:
        s: The raw path string.

    Returns:
        Escaped path safe for use in ffmpeg filter option values.
    """
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace(":", "\\:")
    s = s.replace(",", "\\,")
    s = s.replace("[", "\\[")
    s = s.replace("]", "\\]")
    s = s.replace(" ", "\\ ")
    return s


# Named colors → ASS BGR hex format (&HAABBGGRR)
_ASS_COLOR_MAP = {
    "white": "&H00FFFFFF",
    "black": "&H00000000",
    "red": "&H000000FF",
    "green": "&H0000FF00",
    "blue": "&H00FF0000",
    "yellow": "&H0000FFFF",
    "cyan": "&H00FFFF00",
    "magenta": "&H00FF00FF",
    "gray": "&H00808080",
    "grey": "&H00808080",
}


def color_to_ass_bgr(color: str, default: str = "&H00FFFFFF") -> str:
    """Convert a color name, hex string, or ASS color to ASS BGR format.

    Supports:
    - Named colors: white, black, red, green, blue, yellow, cyan,
      magenta, gray/grey
    - 6-digit hex: #RRGGBB → &H00BBGGRR
    - 8-digit hex with alpha: #AARRGGBB → &HAABBGGRR
    - Native ASS colors: &H... passed through unchanged

    Args:
        color: Color string in any supported format.
        default: Fallback ASS color if parsing fails.

    Returns:
        ASS-format BGR hex string like ``&H00FFFFFF``.
    """
    c = color.lower().strip()
    if c in _ASS_COLOR_MAP:
        return _ASS_COLOR_MAP[c]
    if c.startswith("#") and len(c) in (7, 9):
        hex_val = c.lstrip("#")
        if not all(ch in "0123456789abcdef" for ch in hex_val):
            return default  # Invalid hex digits
        if len(hex_val) == 6:
            r, g, b = hex_val[0:2], hex_val[2:4], hex_val[4:6]
            return f"&H00{b}{g}{r}".upper()
        else:
            a, r, g, b = hex_val[0:2], hex_val[2:4], hex_val[4:6], hex_val[6:8]
            return f"&H{a}{b}{g}{r}".upper()
    if c.startswith("&h"):
        return color  # native ASS pass-through
    return default


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
    # Optimization: avoid computing redaction if key not present in text
    if api_key not in text:
        return text
    return text.replace(api_key, redact_secret(api_key))
