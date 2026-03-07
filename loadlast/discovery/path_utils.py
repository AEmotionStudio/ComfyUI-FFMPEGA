"""
Path sandboxing utilities for LoadLast nodes.

Validates that user-supplied paths are within ComfyUI's allowed
directories (output, temp, input) to prevent arbitrary filesystem
access.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

try:
    import folder_paths
except ImportError:
    folder_paths = None  # type: ignore[assignment]


def get_allowed_directories() -> list[str]:
    """Return the set of directories users are allowed to access."""
    if folder_paths is None:
        return []
    dirs = []
    for getter in (
        folder_paths.get_output_directory,
        folder_paths.get_temp_directory,
        folder_paths.get_input_directory,
    ):
        try:
            dirs.append(os.path.realpath(getter()))
        except Exception:
            pass
    return dirs


def get_scan_directories() -> list[str]:
    """Return ComfyUI's output and temp directories for scanning."""
    if folder_paths is None:
        return []
    dirs = []
    try:
        d = os.path.realpath(folder_paths.get_output_directory())
        if d and os.path.isdir(d):
            dirs.append(d)
    except Exception:
        pass
    try:
        d = os.path.realpath(folder_paths.get_temp_directory())
        if d and os.path.isdir(d):
            dirs.append(d)
    except Exception:
        pass
    return dirs


def is_path_sandboxed(path: str) -> bool:
    """Check if a path is within ComfyUI's allowed directories."""
    real = os.path.realpath(path)
    for allowed in get_allowed_directories():
        try:
            if os.path.commonpath([allowed, real]) == allowed:
                return True
        except ValueError:
            continue
    return False


def resolve_scan_dirs(source: str) -> list[str]:
    """Return scan directories for a user-supplied source path.

    If *source* is a valid, sandboxed directory, return it as the sole entry.
    Otherwise fall back to the default ComfyUI output/temp directories.
    """
    s = source.strip() if source else ""
    if s:
        s = os.path.realpath(s)
        if not os.path.isdir(s):
            logger.warning("[LoadLast] source '%s' is not a directory, using defaults", s)
        elif not is_path_sandboxed(s):
            logger.warning("[LoadLast] source '%s' is outside allowed directories, using defaults", s)
        else:
            return [s]
    return get_scan_directories()
