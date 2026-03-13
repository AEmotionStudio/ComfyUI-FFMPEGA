"""Filter preset builder for the Video Editor export pipeline.

Maps preset names (cinematic, vintage, noir, etc.) to FFmpeg filter chains.
Reuses the exact filter expressions from ``skills/handlers/visual.py``
where possible and adds new ones for the NLE editor.

If an intensity < 1.0 is specified, uses a ``split → apply → blend`` pattern
to blend the filtered output with the original at the given opacity.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("ffmpega.videoeditor")

# ── Preset → simple -vf filter map ──────────────────────────────────
# These are straightforward -vf chains (not filter_complex).

_SIMPLE_PRESETS: dict[str, str] = {
    "cinematic":     "eq=saturation=0.7:contrast=1.2:brightness=-0.05",
    "vintage":       "eq=saturation=0.6:contrast=1.1,colorbalance=rs=0.15:gs=0.05:bs=-0.1",
    "noir":          "eq=saturation=0.0:contrast=1.3:brightness=-0.1,curves=preset=cross_process",
    "cyberpunk":     "eq=saturation=1.6:contrast=1.3:brightness=0.05,colorbalance=bs=0.2:bm=0.1:gs=-0.1",
    "lofi":          "eq=saturation=0.5:contrast=0.9:brightness=0.1,colorbalance=rs=0.1:bs=-0.05",
    "sepia":         "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "bleach_bypass": "eq=saturation=0.4:contrast=1.5:brightness=-0.05,unsharp=5:5:0.8",
    "dream":         "gblur=sigma=2,eq=brightness=0.15:saturation=0.8:contrast=0.9",
    "film_grain":    "eq=saturation=0.85:contrast=1.1,noise=alls=20:allf=t",
    "b_and_w":       "eq=saturation=0.0:contrast=1.1",
    "warm":          "colortemperature=temperature=7500,eq=saturation=1.1",
    "cool":          "colortemperature=temperature=4000,eq=saturation=1.05:brightness=-0.03",
    "neon":          "eq=saturation=3.0:brightness=0.1",
    "thermal": (
        "pseudocolor="
        "c0='if(between(val,0,85),255,if(between(val,85,170),255,if(between(val,170,255),255,0)))':"
        "c1='if(between(val,0,85),0,if(between(val,85,170),val*3-255,if(between(val,170,255),255,0)))':"
        "c2='if(between(val,0,85),0,if(between(val,85,170),0,if(between(val,170,255),val*3-510,0)))'"
    ),
}

# ── Complex presets (filter_complex) ─────────────────────────────────
# These require split/blend and can't be expressed as simple -vf chains.

_COMPLEX_PRESETS: dict[str, str] = {
    "comic_book": (
        "[0:v]split[a][b];"
        "[b]edgedetect=low=0.1:high=0.4,negate[b];"
        "[a]lutrgb=r='trunc(val/42)*42':g='trunc(val/42)*42':b='trunc(val/42)*42',"
        "eq=saturation=1.5:contrast=1.3[a];"
        "[a][b]blend=all_mode=multiply[out]"
    ),
}

# Human-readable labels for the frontend (order matches FiltersPanel.ts)
PRESET_NAMES: list[str] = list(_SIMPLE_PRESETS.keys()) + list(_COMPLEX_PRESETS.keys())


def build_filter_preset(preset_json: str) -> tuple[list[str], str]:
    """Parse *preset_json* and return FFmpeg filter args.

    Parameters
    ----------
    preset_json:
        JSON string from the ``_filter_preset`` hidden widget, e.g.
        ``{"preset": "cinematic", "intensity": 0.8}``.

    Returns
    -------
    tuple[list[str], str]
        A 2-tuple of ``(vf_filters, filter_complex)``.
        * If the preset is "simple", ``vf_filters`` is populated and
          ``filter_complex`` is empty.
        * If the preset is "complex" (e.g. comic_book), ``vf_filters``
          is empty and ``filter_complex`` has the full chain.
        * Both empty means nothing to apply.
    """
    if not preset_json or not preset_json.strip() or preset_json == "{}":
        return [], ""

    try:
        state = json.loads(preset_json)
    except (json.JSONDecodeError, TypeError):
        log.warning("[VideoEditor] Invalid filter preset JSON: %.100s", preset_json)
        return [], ""

    if not isinstance(state, dict):
        return [], ""

    name = str(state.get("preset", "")).strip().lower()
    if not name or name == "none":
        return [], ""

    intensity = max(0.0, min(1.0, float(state.get("intensity", 1.0))))

    # ── Simple preset ──
    if name in _SIMPLE_PRESETS:
        vf = _SIMPLE_PRESETS[name]
        if intensity >= 0.99:
            return [vf], ""
        # Blend at reduced intensity using split → apply → blend
        fc = (
            f"[0:v]split[orig][eff];"
            f"[eff]{vf}[eff];"
            f"[orig][eff]blend=all_mode=normal:all_opacity={intensity:.2f}[out]"
        )
        return [], fc

    # ── Complex preset ──
    if name in _COMPLEX_PRESETS:
        fc = _COMPLEX_PRESETS[name]
        if intensity < 0.99:
            # Wrap in a split → blend for intensity control.
            # Complex presets reference [0:v] directly, so we must replace
            # that with the split output [__in] to avoid consuming [0:v] twice.
            # Also replace the original [out] with [__eff] so we don't produce
            # a double output label (e.g. [out][__eff]).
            inner_fc = fc.replace("[0:v]", "[__in]").replace("[out]", "[__eff]")
            fc = (
                f"[0:v]split[__orig][__in];"
                f"{inner_fc};"
                f"[__orig][__eff]blend=all_mode=normal:all_opacity={intensity:.2f}[out]"
            )
        return [], fc

    log.warning("[VideoEditor] Unknown filter preset: %s", name)
    return [], ""


def has_filter_preset(preset_json: str) -> bool:
    """Quick check whether the preset JSON specifies a non-empty preset."""
    if not preset_json or not preset_json.strip() or preset_json == "{}":
        return False
    try:
        state = json.loads(preset_json)
        name = str(state.get("preset", "")).strip().lower()
        return bool(name) and name != "none"
    except (json.JSONDecodeError, TypeError):
        return False
