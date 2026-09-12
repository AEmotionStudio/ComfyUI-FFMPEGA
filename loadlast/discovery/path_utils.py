"""
Path sandboxing — the single authority for the whole extension.

Validates that user-supplied paths are within ComfyUI's allowed directories
(output, temp, input) or FFMPEGA's own ``ffmpega_*`` scratch space under the
system temp directory, to prevent arbitrary filesystem access.

Every path check across the extension — server routes, node inputs, the video
editor export — delegates here rather than re-implementing the rule, so it
cannot drift between copies (which is exactly how the tempdir check ended up
too wide in several places before this was consolidated).
"""

from __future__ import annotations

import logging
import os
import tempfile

logger = logging.getLogger(__name__)

# Track already-warned source paths to avoid spamming the console.
# These functions are called on every JS poll (~5 s) and every
# IS_CHANGED scheduler tick, so a repeated warning is pure noise.
_warned_sources: set[str] = set()

try:
    import folder_paths
except ImportError:
    folder_paths = None  # type: ignore[assignment]


def get_allowed_directories() -> list[str]:
    """Return the set of directories users are allowed to access.

    Resolved defensively: a ``folder_paths`` that is missing one of the
    getters (e.g. a partial stub) skips that directory rather than raising, so
    a path check never crashes the route it guards.
    """
    if folder_paths is None:
        return []
    dirs = []
    for name in ("get_output_directory", "get_temp_directory", "get_input_directory"):
        getter = getattr(folder_paths, name, None)
        if getter is None:
            continue
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


def _is_ffmpega_scratch(real: str) -> bool:
    """True only for FFMPEGA's own ``ffmpega_*`` entries under the system tempdir.

    Preview renders land in ``mkdtemp(prefix="ffmpega_")`` and transcodes /
    extracted first frames in ``ffmpega_preview_*`` / ``ffmpega_frame_*`` there,
    so those must be accepted. Anything else in the tempdir belongs to another
    process and must not be — accepting the whole tempdir over an
    unauthenticated route is an arbitrary-file-read hole.

    *real* must already be an ``os.path.realpath``.
    """
    sys_tmp = os.path.realpath(tempfile.gettempdir())
    if real != sys_tmp and not real.startswith(sys_tmp + os.sep):
        return False
    rel = real[len(sys_tmp):].lstrip(os.sep)
    if not rel:
        return False  # the tempdir itself
    return rel.split(os.sep)[0].startswith("ffmpega_")


def is_path_sandboxed(path: str) -> bool:
    """True if *path* is inside ComfyUI's allowed dirs or FFMPEGA scratch.

    The single authority for path sandboxing — see the module docstring.
    """
    real = os.path.realpath(path)
    for allowed in get_allowed_directories():
        if real == allowed or real.startswith(allowed + os.sep):
            return True
    return _is_ffmpega_scratch(real)


def resolve_scan_dirs(source: str) -> list[str]:
    """Return scan directories for a user-supplied source path.

    If *source* is a valid, sandboxed directory, return it as the sole entry.
    Otherwise fall back to the default ComfyUI output/temp directories.
    """
    s = source.strip() if source else ""
    if s:
        s = os.path.realpath(s)
        if not os.path.isdir(s):
            if s not in _warned_sources:
                _warned_sources.add(s)
                logger.warning("[LoadLast] source '%s' is not a directory, using defaults", s)
        elif not is_path_sandboxed(s):
            if s not in _warned_sources:
                _warned_sources.add(s)
                logger.warning("[LoadLast] source '%s' is outside allowed directories, using defaults", s)
        else:
            return [s]
    return get_scan_directories()
