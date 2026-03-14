"""Compositing filters for PiP, watermark, chroma key, blend, etc.

All functions return FFmpeg filter strings or `-filter_complex`
arguments to be applied during the export pipeline.
"""

from __future__ import annotations

import json
import logging
import math

log = logging.getLogger("ffmpega.videoeditor")


# ── PiP (Picture-in-Picture) ────────────────────────────────────────

def build_pip_filter(params: dict) -> str | None:
    """Build an FFmpeg ``-filter_complex`` for PiP overlay.

    The caller must supply the overlay source as a second input (``-i``).

    Parameters
    ----------
    params : dict
        Keys: ``enabled``, ``position`` (preset string or "custom"),
        ``x``, ``y``, ``size`` (0–100%), ``opacity`` (0–100%),
        ``start_time``, ``end_time``, ``border``, ``border_color``,
        ``border_width``.

    Returns
    -------
    str or None
        FFmpeg ``-filter_complex`` string, or None if disabled.
    """
    if not params.get("enabled"):
        return None

    size_pct = max(5, min(100, params.get("size", 25))) / 100.0
    opacity = max(0, min(100, params.get("opacity", 100))) / 100.0
    position = params.get("position", "bottom-right")
    custom_x = params.get("x", 0)
    custom_y = params.get("y", 0)
    start = params.get("start_time")
    end = params.get("end_time")
    border = params.get("border", False)
    border_color = params.get("border_color", "white")
    border_width = max(0, min(20, params.get("border_width", 2)))

    # Overlay input scaling
    parts: list[str] = []
    parts.append(f"[1:v]scale=iw*{size_pct:.3f}:-2")

    # Border
    if border and border_width > 0:
        bw = border_width
        bc = _sanitize_color(border_color)
        parts[-1] += f",pad=iw+{bw * 2}:ih+{bw * 2}:{bw}:{bw}:{bc}"

    # Opacity
    if opacity < 1.0:
        parts[-1] += f",format=rgba,colorchannelmixer=aa={opacity:.2f}"

    parts[-1] += "[pip]"

    # Position calculation
    x_expr, y_expr = _position_to_xy(position, custom_x, custom_y)

    # Overlay with timing
    overlay = f"[0:v][pip]overlay={x_expr}:{y_expr}"
    if start is not None or end is not None:
        s = float(start) if start is not None else 0
        e = float(end) if end is not None else 9999
        overlay += f":enable='between(t,{s:.2f},{e:.2f})'"

    parts.append(overlay)
    return ";".join(parts)


def build_watermark_filter(params: dict) -> str | None:
    """Build FFmpeg filter for a static image watermark.

    Unlike PiP, watermark uses ``movie=`` as a filter source
    so it doesn't require a second ``-i`` input.

    Parameters
    ----------
    params : dict
        Keys: ``enabled``, ``path``, ``position``, ``x``, ``y``,
        ``size`` (%), ``opacity`` (%), ``persistent`` (bool).
    """
    if not params.get("enabled"):
        return None

    path = params.get("path", "")
    if not path:
        return None

    size_pct = max(5, min(100, params.get("size", 15))) / 100.0
    opacity = max(0, min(100, params.get("opacity", 80))) / 100.0
    position = params.get("position", "bottom-right")
    custom_x = params.get("x", 0)
    custom_y = params.get("y", 0)

    # Escape path for FFmpeg filter_complex metacharacters
    escaped_path = (
        path
        .replace("\\", "/")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(";", "\\;")
    )
    parts: list[str] = []

    # Load and scale the watermark
    wm_filter = f"movie={escaped_path}"
    wm_filter += f",scale=iw*{size_pct:.3f}:-2"

    if opacity < 1.0:
        wm_filter += f",format=rgba,colorchannelmixer=aa={opacity:.2f}"

    wm_filter += "[wm]"
    parts.append(wm_filter)

    x_expr, y_expr = _position_to_xy(position, custom_x, custom_y)
    parts.append(f"[0:v][wm]overlay={x_expr}:{y_expr}")

    return ";".join(parts)


# ── Chroma Key ──────────────────────────────────────────────────────

def build_chromakey_filter(params: dict) -> list[str]:
    """Build FFmpeg chromakey/colorkey filters.

    Parameters
    ----------
    params : dict
        Keys: ``enabled``, ``color`` (hex), ``similarity`` (0–1),
        ``blend`` (0–1), ``mode`` ("chromakey" or "colorkey").

    Returns
    -------
    list[str]
        Filter strings to chain.
    """
    if not params.get("enabled"):
        return []

    color = _sanitize_color(params.get("color", "0x00ff00"))
    similarity = max(0.01, min(1.0, params.get("similarity", 0.3)))
    blend = max(0.0, min(1.0, params.get("blend", 0.1)))
    mode = params.get("mode", "chromakey")

    if mode not in ("chromakey", "colorkey"):
        mode = "chromakey"

    return [f"{mode}={color}:{similarity:.2f}:{blend:.2f}"]


# ── Blend Modes ─────────────────────────────────────────────────────

_VALID_BLEND_MODES = {
    "normal", "multiply", "screen", "overlay", "difference",
    "addition", "subtract", "dodge", "burn", "hardlight",
    "softlight", "exclusion", "darken", "lighten",
}


def build_blend_filter(params: dict) -> list[str]:
    """Build FFmpeg blend filter for two-input compositing.

    Parameters
    ----------
    params : dict
        Keys: ``enabled``, ``mode``, ``opacity`` (0–1).
    """
    if not params.get("enabled"):
        return []

    mode = params.get("mode", "normal")
    if mode not in _VALID_BLEND_MODES:
        mode = "normal"

    opacity = max(0.0, min(1.0, params.get("opacity", 1.0)))
    return [f"blend=all_mode={mode}:all_opacity={opacity:.2f}"]


# ── Split Screen ────────────────────────────────────────────────────

def build_split_screen_filter(params: dict) -> str | None:
    """Build ``xstack`` filter for multi-source split screen.

    Parameters
    ----------
    params : dict
        Keys: ``enabled``, ``layout`` ("2h", "2v", "3", "4"),
        ``border_width``, ``border_color``.
    """
    if not params.get("enabled"):
        return None

    layout = params.get("layout", "2h")
    bw = max(0, min(10, params.get("border_width", 0)))

    layouts = {
        "2h": {"inputs": 2, "xstack": "0_0|w0_0"},
        "2v": {"inputs": 2, "xstack": "0_0|0_h0"},
        "3":  {"inputs": 3, "xstack": "0_0|w0_0|0_h0"},
        "4":  {"inputs": 4, "xstack": "0_0|w0_0|0_h0|w0_h0"},
    }

    cfg = layouts.get(layout)
    if not cfg:
        return None

    return f"xstack=inputs={cfg['inputs']}:layout={cfg['xstack']}"


# ── Masking ─────────────────────────────────────────────────────────

def build_vignette_filter(params: dict) -> list[str]:
    """Build vignette filter.

    Parameters
    ----------
    params : dict
        Keys: ``enabled``, ``intensity`` (0–100%), ``softness`` (0–1).
    """
    if not params.get("enabled"):
        return []

    intensity = max(0, min(100, params.get("intensity", 50))) / 100.0
    angle = intensity * math.pi / 4  # PI/4 maximum
    return [f"vignette=angle={angle:.4f}"]


def build_mask_filter(params: dict) -> list[str]:
    """Build shape-based mask filter using drawbox + blur.

    Parameters
    ----------
    params : dict
        Keys: ``enabled``, ``shape`` ("circle", "rectangle"),
        ``x``, ``y``, ``width``, ``height``, ``feather``,
        ``invert``, ``effect`` ("blur", "darken", "desaturate").
    """
    if not params.get("enabled"):
        return []

    # Mask is simulated via geq or alphamerge with generated shapes
    # For now, provide drawbox-based rectangular mask
    effect = params.get("effect", "blur")
    x = params.get("x", "iw/4")
    y = params.get("y", "ih/4")
    w = params.get("width", "iw/2")
    h = params.get("height", "ih/2")
    invert = params.get("invert", False)

    filters: list[str] = []

    if effect == "blur":
        # Apply blur to the whole frame, then overlay the original inside the mask area
        if invert:
            filters.append(f"boxblur=10:10")
        else:
            # Blur outside the box — complex, use drawbox with invert for now
            filters.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black@0.5:t=fill")
    elif effect == "darken":
        filters.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black@0.5:t=fill")
    elif effect == "desaturate":
        filters.append("hue=s=0")

    return filters


# ── Onion Skin (temporal ghost trail) ───────────────────────────────

def build_onion_skin_filter(params: dict) -> list[str]:
    """Build lagfun filter for temporal onion skin (ghost trail).

    In the NLE editor context, onion skin operates on a single source
    video using temporal self-blending.

    Parameters
    ----------
    params : dict
        Keys: ``enabled``, ``blend_mode`` (for tblend), ``opacity`` (0–100%),
        ``decay`` (0.9–0.999).
    """
    if not params.get("enabled"):
        return []

    decay = max(0.9, min(0.999, params.get("decay", 0.97)))
    return [f"lagfun=decay={decay}"]


# ── Compose State ───────────────────────────────────────────────────

def has_compose(compose_json: str) -> bool:
    """Quick check if any compositing is configured."""
    if not compose_json or not compose_json.strip() or compose_json == "{}":
        return False
    try:
        data = json.loads(compose_json)
        if not isinstance(data, dict):
            return False
        # Check if any subsection is enabled
        for key in ("pip", "watermark", "chromakey", "blend", "splitScreen", "vignette", "mask", "onionSkin"):
            section = data.get(key)
            if isinstance(section, dict) and section.get("enabled"):
                return True
        return False
    except (json.JSONDecodeError, TypeError):
        return False


def build_compose_filters(compose_json: str) -> dict:
    """Parse compose JSON and return structured filter collection.

    Returns
    -------
    dict with keys:
        ``pip_filter``: str or None (filter_complex for PiP)
        ``watermark_filter``: str or None (filter_complex for watermark)
        ``chromakey``: list[str] (video filters)
        ``blend``: list[str] (blend filters)
        ``split_screen``: str or None (xstack filter_complex)
        ``vignette``: list[str] (video filters)
        ``mask``: list[str] (video filters)
    """
    result = {
        "pip_filter": None,
        "watermark_filter": None,
        "chromakey": [],
        "blend": [],
        "split_screen": None,
        "vignette": [],
        "mask": [],
        "onion_skin": [],
    }

    if not compose_json or not compose_json.strip() or compose_json == "{}":
        return result

    try:
        data = json.loads(compose_json)
    except (json.JSONDecodeError, TypeError):
        return result

    if not isinstance(data, dict):
        return result

    pip = data.get("pip")
    if isinstance(pip, dict):
        result["pip_filter"] = build_pip_filter(pip)

    wm = data.get("watermark")
    if isinstance(wm, dict):
        result["watermark_filter"] = build_watermark_filter(wm)

    ck = data.get("chromakey")
    if isinstance(ck, dict):
        result["chromakey"] = build_chromakey_filter(ck)

    bl = data.get("blend")
    if isinstance(bl, dict):
        result["blend"] = build_blend_filter(bl)

    ss = data.get("splitScreen")
    if isinstance(ss, dict):
        result["split_screen"] = build_split_screen_filter(ss)

    vig = data.get("vignette")
    if isinstance(vig, dict):
        result["vignette"] = build_vignette_filter(vig)

    msk = data.get("mask")
    if isinstance(msk, dict):
        result["mask"] = build_mask_filter(msk)

    oskin = data.get("onionSkin")
    if isinstance(oskin, dict):
        result["onion_skin"] = build_onion_skin_filter(oskin)

    return result


# ── Helpers ─────────────────────────────────────────────────────────

_POSITION_MAP = {
    "top-left":     ("10", "10"),
    "top-right":    ("W-w-10", "10"),
    "bottom-left":  ("10", "H-h-10"),
    "bottom-right": ("W-w-10", "H-h-10"),
    "center":       ("(W-w)/2", "(H-h)/2"),
    "top-center":   ("(W-w)/2", "10"),
    "bottom-center":("(W-w)/2", "H-h-10"),
}


def _position_to_xy(
    position: str, custom_x: int | float = 0, custom_y: int | float = 0,
) -> tuple[str, str]:
    """Convert position preset to overlay x:y expressions."""
    if position == "custom":
        return (str(int(custom_x)), str(int(custom_y)))
    return _POSITION_MAP.get(position, ("W-w-10", "H-h-10"))


def _sanitize_color(color: str) -> str:
    """Normalize a color value for FFmpeg.

    Converts ``#rrggbb`` → ``0xrrggbb``, passes through named FFmpeg
    colors (e.g. ``white``, ``black``), and strips invalid chars from
    hex values.
    """
    color = color.strip()
    if color.startswith("#"):
        color = "0x" + color[1:]
    # Allow named FFmpeg colors (e.g. "white", "black", "green")
    if color.isalpha():
        return color
    # Remove any non-hex characters (safety)
    allowed = set("0123456789abcdefABCDEFx")
    return "".join(c for c in color if c in allowed) or "0xffffff"
