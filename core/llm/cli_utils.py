"""CLI binary resolution — shared helper for all CLI-based LLM connectors.

The ComfyUI virtual-environment may have a narrowed ``PATH`` that
excludes user-local directories such as ``~/.local/bin`` or
``~/.local/share/pnpm``.  This module provides a single
:func:`resolve_cli_binary` helper that both the auto-detection code
in ``agent_node.py`` and the individual CLI connectors can use to
locate binaries reliably.

Supports **Linux**, **macOS**, and **Windows**.
"""

import os
import pathlib
import platform
import shutil
from typing import Optional


def _build_search_dirs() -> list[pathlib.Path]:
    """Build a list of well-known directories where npm/pnpm/pipx install
    global binaries, based on the current platform."""

    home = pathlib.Path.home()
    dirs: list[pathlib.Path] = []
    system = platform.system()

    if system == "Windows":
        # npm global: %APPDATA%\npm
        appdata = os.environ.get("APPDATA")
        if appdata:
            dirs.append(pathlib.Path(appdata) / "npm")

        # pnpm global: %LOCALAPPDATA%\pnpm
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            dirs.append(pathlib.Path(localappdata) / "pnpm")

        # nvm-windows: %APPDATA%\nvm
        if appdata:
            dirs.append(pathlib.Path(appdata) / "nvm")

        # Scoop shims (popular Windows package manager)
        dirs.append(home / "scoop" / "shims")

    else:
        # Linux + macOS shared paths
        dirs.append(home / ".local" / "bin")              # pipx, user installs
        dirs.append(home / ".local" / "share" / "pnpm")   # pnpm global
        dirs.append(home / ".nvm" / "versions")            # nvm global
        dirs.append(pathlib.Path("/usr/local/bin"))         # Homebrew (Intel Mac) / manual installs

        if system == "Darwin":
            # Homebrew on Apple Silicon
            dirs.append(pathlib.Path("/opt/homebrew/bin"))
            # macOS npm global default
            dirs.append(pathlib.Path("/usr/local/lib/node_modules/.bin"))

    return dirs


_EXTRA_SEARCH_DIRS = _build_search_dirs()


def resolve_cli_binary(*names: str) -> Optional[str]:
    """Return the full path to the first binary found, or ``None``.

    Checks ``shutil.which`` first (uses the current ``PATH``), then
    falls back to probing well-known user-local directories.

    Works on Linux, macOS, and Windows.

    Parameters
    ----------
    *names : str
        One or more candidate binary names to look for, e.g.
        ``"qwen"``, ``"qwen.cmd"``.

    Returns
    -------
    str | None
        Absolute path to the binary, or ``None`` if not found.
    """
    # Fast-path: binary is already on PATH
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    # Fallback: check well-known directories
    for directory in _EXTRA_SEARCH_DIRS:
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return str(candidate)

    return None
