"""Expression preset save/load for LivePortrait.

Stores presets as JSON files in ComfyUI's output directory under
``exp_data/``.  Each preset is a simple dict with expression parameter
values that can be loaded and applied to the animate_portrait sliders.
"""

import json
import logging
import os
from typing import Optional

log = logging.getLogger("ffmpega")

# Expression parameter names (must match synthesizer + handler)
EXPR_KEYS = (
    "rotate_pitch", "rotate_yaw", "rotate_roll",
    "blink", "eyebrow", "wink",
    "pupil_x", "pupil_y",
    "aaa", "eee", "woo", "smile",
    "retargeting_eyes", "retargeting_mouth",
    "crop_factor",
)

# Default values (0 for expressions, 1 for retargeting, 1.6 for crop)
DEFAULTS = {
    "rotate_pitch": 0.0, "rotate_yaw": 0.0, "rotate_roll": 0.0,
    "blink": 0.0, "eyebrow": 0.0, "wink": 0.0,
    "pupil_x": 0.0, "pupil_y": 0.0,
    "aaa": 0.0, "eee": 0.0, "woo": 0.0, "smile": 0.0,
    "retargeting_eyes": 1.0, "retargeting_mouth": 1.0,
    "crop_factor": 1.6,
}


def _presets_dir() -> str:
    """Return the expression presets directory, creating it if needed."""
    # Try ComfyUI output dir first
    try:
        import folder_paths  # type: ignore[import-not-found]
        base = folder_paths.get_output_directory()
    except (ImportError, AttributeError):
        base = os.path.join(os.path.expanduser("~"), "ComfyUI", "output")
    d = os.path.join(base, "exp_data")
    os.makedirs(d, exist_ok=True)
    return d


def save_expression(name: str, params: dict) -> str:
    """Save expression parameters as a named preset.

    Args:
        name: Preset name (will be sanitized for filesystem).
        params: Dict of expression parameter values. Keys should be
            from EXPR_KEYS; unknown keys are ignored.

    Returns:
        Full path to the saved JSON file.
    """
    # Sanitize name
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
    safe = safe.strip() or "unnamed"

    # Extract only known keys, fill missing with defaults
    data = {}
    for key in EXPR_KEYS:
        val = params.get(key, params.get(f"lp_{key}", DEFAULTS.get(key, 0.0)))
        try:
            data[key] = float(val)
        except (TypeError, ValueError):
            data[key] = DEFAULTS.get(key, 0.0)

    path = os.path.join(_presets_dir(), f"{safe}.json")
    with open(path, "w") as f:
        json.dump({"name": name, "params": data}, f, indent=2)

    log.info("[ExprPreset] Saved '%s' → %s", name, path)
    return path


def load_expression(name: str) -> Optional[dict]:
    """Load an expression preset by name.

    Args:
        name: Preset name (without .json extension).

    Returns:
        Dict of expression parameter values, or None if not found.
    """
    path = os.path.join(_presets_dir(), f"{name}.json")
    if not os.path.isfile(path):
        log.warning("[ExprPreset] Preset not found: %s", path)
        return None

    with open(path) as f:
        data = json.load(f)

    return data.get("params", data)


def list_expressions() -> list[str]:
    """List available expression preset names.

    Returns:
        Sorted list of preset names (without .json extension).
    """
    d = _presets_dir()
    names = []
    for fname in os.listdir(d):
        if fname.endswith(".json"):
            names.append(fname[:-5])
    names.sort()
    return names


def delete_expression(name: str) -> bool:
    """Delete an expression preset by name.

    Returns:
        True if deleted, False if not found.
    """
    path = os.path.join(_presets_dir(), f"{name}.json")
    if os.path.isfile(path):
        os.remove(path)
        log.info("[ExprPreset] Deleted '%s'", name)
        return True
    return False
