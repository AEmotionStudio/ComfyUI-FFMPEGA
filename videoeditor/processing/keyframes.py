"""Keyframe interpolation → FFmpeg expression converter.

Converts a list of keyframe dicts ``[{time, value, easing}, ...]``
into an FFmpeg expression string using nested ``if(between(t,...),...)``
statements.

Used by the export pipeline for speed ramps (``setpts``) and volume
automation (``volume``).
"""

from __future__ import annotations

import json
import logging
import math

log = logging.getLogger("ffmpega.videoeditor")


def keyframes_to_ffmpeg_expr(keyframes_json: str, prop: str = "speed") -> str | None:
    """Convert keyframe JSON to an FFmpeg expression.

    Parameters
    ----------
    keyframes_json:
        JSON string ``{"keyframes": [{time, value, easing}, ...], ...}``
    prop:
        Property name (``"speed"`` or ``"volume"``), affects how the
        expression is formatted.

    Returns
    -------
    str | None
        FFmpeg expression string, or ``None`` if no keyframes found.
    """
    if not keyframes_json or not keyframes_json.strip() or keyframes_json in ("{}", "[]"):
        return None

    try:
        data = json.loads(keyframes_json)
    except (json.JSONDecodeError, TypeError):
        log.warning("[VideoEditor] Invalid keyframes JSON: %.100s", keyframes_json)
        return None

    if not isinstance(data, dict):
        return None

    kfs = data.get("keyframes", [])
    if not isinstance(kfs, list) or len(kfs) < 2:
        # Need at least 2 keyframes for interpolation
        return None

    # Sort by time
    kfs = sorted(kfs, key=lambda k: float(k.get("time", 0)))

    # Build nested if/between expressions
    # For each pair of keyframes, generate: if(between(t, t0, t1), lerp_expr, ...)
    parts: list[str] = []

    for i in range(len(kfs) - 1):
        t0 = float(kfs[i]["time"])
        v0 = float(kfs[i]["value"])
        t1 = float(kfs[i + 1]["time"])
        v1 = float(kfs[i + 1]["value"])
        easing = str(kfs[i].get("easing", "linear"))

        if t1 - t0 < 0.001:
            continue

        lerp_expr = _build_lerp(t0, v0, t1, v1, easing)
        parts.append(f"if(between(t,{t0:.3f},{t1:.3f}),{lerp_expr}")

    if not parts:
        return None

    # Clamp before first keyframe to first value, after last to last value
    first_val = float(kfs[0]["value"])
    last_val = float(kfs[-1]["value"])
    first_time = float(kfs[0]["time"])

    # Build: if(lt(t,first_time), first_val, if(between(t,...), ..., last_val))
    # Nest from inside out
    expr = f"{last_val:.4f}"
    for part in reversed(parts):
        expr = f"{part},{expr})"

    expr = f"if(lt(t,{first_time:.3f}),{first_val:.4f},{expr})"

    return expr


def build_speed_keyframe_filter(keyframes_json: str) -> str | None:
    """Build a ``setpts`` expression for speed keyframes.

    Speed keyframes define a variable speed multiplier over time.
    The ``setpts`` filter requires: ``setpts=PTS/speed_expr``

    Returns
    -------
    str | None
        e.g. ``setpts=PTS/(if(between(t,...),...))``, or ``None``.
    """
    expr = keyframes_to_ffmpeg_expr(keyframes_json, "speed")
    if expr is None:
        return None
    return f"setpts=PTS/({expr})"


def build_volume_keyframe_filter(keyframes_json: str) -> str | None:
    """Build a ``volume`` expression for volume automation keyframes.

    Returns
    -------
    str | None
        e.g. ``volume='if(between(t,...),...)':eval=frame``, or ``None``.
    """
    expr = keyframes_to_ffmpeg_expr(keyframes_json, "volume")
    if expr is None:
        return None
    return f"volume='{expr}':eval=frame"


def has_keyframes(keyframes_json: str) -> bool:
    """Quick check whether keyframe data is non-empty and has >= 2 keyframes."""
    if not keyframes_json or not keyframes_json.strip() or keyframes_json in ("{}", "[]"):
        return False
    try:
        data = json.loads(keyframes_json)
        kfs = data.get("keyframes", [])
        return isinstance(kfs, list) and len(kfs) >= 2
    except (json.JSONDecodeError, TypeError):
        return False


# ── Easing helpers ─────────────────────────────────────────────────

def _build_lerp(
    t0: float, v0: float, t1: float, v1: float, easing: str,
) -> str:
    """Build an FFmpeg expression for interpolated value between two keyframes.

    For linear: ``v0 + (v1-v0) * (t-t0)/(t1-t0)``
    For ease-in: quadratic: ``v0 + (v1-v0) * ((t-t0)/(t1-t0))^2``
    For ease-out: ``v0 + (v1-v0) * (1 - (1 - (t-t0)/(t1-t0))^2)``
    For ease-in-out: smoothstep
    For step: just v0
    """
    dt = t1 - t0
    dv = v1 - v0

    if abs(dv) < 0.0001:
        return f"{v0:.4f}"

    progress = f"(t-{t0:.3f})/{dt:.3f}"

    if easing == "step":
        return f"{v0:.4f}"
    elif easing == "ease-in":
        # Quadratic ease-in: v0 + dv * p^2
        return f"{v0:.4f}+{dv:.4f}*pow({progress},2)"
    elif easing == "ease-out":
        # Quadratic ease-out: v0 + dv * (1 - (1-p)^2)
        return f"{v0:.4f}+{dv:.4f}*(1-pow(1-{progress},2))"
    elif easing == "ease-in-out":
        # Smoothstep: v0 + dv * (3p^2 - 2p^3)
        p = progress
        return f"{v0:.4f}+{dv:.4f}*(3*pow({p},2)-2*pow({p},3))"
    else:
        # Linear: v0 + dv * p
        return f"{v0:.4f}+{dv:.4f}*{progress}"
